# -*- coding: utf-8 -*-
"""IPL Auction Arena - backend with rooms.
Run: ./venv/bin/python app.py   (serves on http://0.0.0.0:5000)

Rooms: the first page lets a user create a room (getting a 6-letter code) or
join one. Inside a room, each bidder picks one team; a team is locked once
taken. All auction state (bidders, players, auction, events) is scoped to the
room code.
"""
import json
import os
import secrets
import sqlite3
import threading
import time
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory

import hashlib
import hmac
import re
import smtplib
import ssl
from email.message import EmailMessage

from data import TEAMS, MODES, PLAYERS

BASE = Path(__file__).resolve().parent
DB_PATH = BASE / "auction.db"
STATIC_DIR = BASE / "static"

BID_WINDOW = 20      # seconds of bidding per player
BID_EXTEND = 5       # seconds added to the clock on every new bid
RESULT_SECS = 7      # celebration screen before auto-advancing
MIN_BASE_LAKH = 30   # cheapest possible base price (solvency rule)

CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"  # no confusing 0/O/1/I

# Career stats (IPL): {"Player Name": {"mat":..,"runs":..,"wkts":..}}. Built by
# research; missing file or missing player simply means "no stats shown".
try:
    with open(BASE / "stats.json", encoding="utf-8") as _f:
        STATS = json.load(_f)
except Exception:
    STATS = {}


def with_stats(row):
    d = dict(row)
    s = STATS.get(d.get("name")) or {}
    d["stats"] = {"mat": s.get("mat"), "runs": s.get("runs"), "wkts": s.get("wkts")}
    return d

app = Flask(__name__)
lock = threading.RLock()


# ---------------------------------------------------------------- db helpers
def db():
    con = sqlite3.connect(DB_PATH, check_same_thread=False)
    con.row_factory = sqlite3.Row
    return con


def init_db():
    con = db()
    c = con.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS rooms(
        code TEXT PRIMARY KEY, host_token TEXT NOT NULL,
        created_at REAL NOT NULL)""")
    c.execute("""CREATE TABLE IF NOT EXISTS bidders(
        id INTEGER PRIMARY KEY, room_code TEXT NOT NULL,
        name TEXT NOT NULL, team_id INTEGER NOT NULL,
        token TEXT UNIQUE NOT NULL, joined_at REAL NOT NULL,
        UNIQUE(room_code, team_id))""")
    c.execute("""CREATE TABLE IF NOT EXISTS players(
        id INTEGER PRIMARY KEY, room_code TEXT NOT NULL,
        name TEXT NOT NULL, country TEXT NOT NULL,
        role TEXT NOT NULL, base_lakh INTEGER NOT NULL, set_name TEXT NOT NULL,
        order_index INTEGER NOT NULL, img TEXT,
        status TEXT NOT NULL DEFAULT 'upcoming',
        sold_price_lakh INTEGER, sold_team_id INTEGER, sold_bidder_id INTEGER)""")
    c.execute("""CREATE TABLE IF NOT EXISTS auction(
        room_code TEXT PRIMARY KEY, mode TEXT, status TEXT NOT NULL DEFAULT 'lobby',
        host_token TEXT, current_player_id INTEGER, current_bid_lakh INTEGER,
        current_bidder_id INTEGER, current_team_id INTEGER,
        bid_deadline REAL, result_until REAL,
        last_player_id INTEGER, last_result TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS events(
        seq INTEGER PRIMARY KEY AUTOINCREMENT, room_code TEXT NOT NULL,
        ts REAL NOT NULL, type TEXT NOT NULL, data TEXT NOT NULL)""")
    # users: OTP accounts are email-based (pw_hash obsolete, name not unique).
    # Fresh DBs get the new schema; old ones are rebuilt, preserving rows.
    has_users = c.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='users'").fetchone()
    if has_users:
        cols = [r["name"] for r in c.execute("PRAGMA table_info(users)").fetchall()]
        if "email" not in cols:
            c.execute("ALTER TABLE users RENAME TO users_old")
            c.execute("""CREATE TABLE users(
                id INTEGER PRIMARY KEY, name TEXT NOT NULL,
                pw_hash TEXT, email TEXT, created_at REAL NOT NULL)""")
            c.execute("INSERT INTO users(id,name,pw_hash,email,created_at)"
                      " SELECT id,name,pw_hash,NULL,created_at FROM users_old")
            c.execute("DROP TABLE users_old")
    else:
        c.execute("""CREATE TABLE users(
            id INTEGER PRIMARY KEY, name TEXT NOT NULL,
            pw_hash TEXT, email TEXT, created_at REAL NOT NULL)""")
    c.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email ON users(email)")
    c.execute("""CREATE TABLE IF NOT EXISTS sessions(
        token TEXT PRIMARY KEY, user_id INTEGER NOT NULL,
        created_at REAL NOT NULL)""")
    c.execute("CREATE INDEX IF NOT EXISTS idx_events_room ON events(room_code, seq)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_players_room ON players(room_code, status)")
    c.execute("""CREATE TABLE IF NOT EXISTS otp_codes(
        id INTEGER PRIMARY KEY, email TEXT NOT NULL, code_hash TEXT NOT NULL,
        created_at REAL NOT NULL, expires_at REAL NOT NULL,
        attempts INTEGER NOT NULL DEFAULT 0, used INTEGER NOT NULL DEFAULT 0)""")
    c.execute("CREATE INDEX IF NOT EXISTS idx_otp_email ON otp_codes(email, id)")
    # rooms.owner_user_id added with lobby start rules; migrate old DBs
    cols = [r["name"] for r in c.execute("PRAGMA table_info(rooms)").fetchall()]
    if "owner_user_id" not in cols:
        c.execute("ALTER TABLE rooms ADD COLUMN owner_user_id INTEGER")
    # bidders.user_id added after rooms shipped; migrate old DBs
    cols = [r["name"] for r in c.execute("PRAGMA table_info(bidders)").fetchall()]
    if "user_id" not in cols:
        c.execute("ALTER TABLE bidders ADD COLUMN user_id INTEGER")
    c.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_bidders_room_user"
              " ON bidders(room_code, user_id)")
    con.commit()
    con.close()


def auth_user(con, token):
    """Return the logged-in user row for a session token, or None."""
    if not token:
        return None
    return con.execute(
        "SELECT u.* FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token=?",
        (token,)).fetchone()


MIN_BIDDERS = 5  # a match cannot start with fewer bidders in the room


def room_owner_id(con, code):
    """Owner of a room: the creator's user id. Legacy rooms (no owner
    recorded) fall back to the earliest-joined bidder still in the room."""
    room = con.execute("SELECT owner_user_id FROM rooms WHERE code=?",
                       (code,)).fetchone()
    if room and room["owner_user_id"]:
        return room["owner_user_id"]
    b = con.execute("SELECT user_id FROM bidders WHERE room_code=?"
                    " AND user_id IS NOT NULL ORDER BY joined_at LIMIT 1",
                    (code,)).fetchone()
    return b["user_id"] if b else None


def new_session(con, user_id):
    token = secrets.token_hex(16)
    con.execute("INSERT INTO sessions(token,user_id,created_at) VALUES (?,?,?)",
                (token, user_id, time.time()))
    return token


def seed_room_players(con, code):
    for i, (name, country, role, base, set_name) in enumerate(PLAYERS):
        con.execute(
            "INSERT INTO players(room_code,name,country,role,base_lakh,set_name,order_index)"
            " VALUES (?,?,?,?,?,?,?)",
            (code, name, country, role, base, set_name, i),
        )


def new_room_code(con):
    for _ in range(30):
        code = "".join(secrets.choice(CODE_ALPHABET) for _ in range(6))
        if not con.execute("SELECT 1 FROM rooms WHERE code=?", (code,)).fetchone():
            return code
    raise RuntimeError("could not generate a room code")


def get_room(con, code):
    code = (code or "").upper().strip()
    return con.execute("SELECT * FROM rooms WHERE code=?", (code,)).fetchone()


def emit(con, code, etype, data):
    con.execute("INSERT INTO events(room_code,ts,type,data) VALUES (?,?,?,?)",
                (code, time.time(), etype, json.dumps(data)))


# ------------------------------------------------------------ auction logic
def next_bid_amount(current_lakh, base_lakh):
    """Official IPL bid increments (in lakh)."""
    if current_lakh is None:
        return base_lakh
    if current_lakh < 100:
        return current_lakh + 5
    if current_lakh < 200:
        return current_lakh + 10
    if current_lakh <= 500:
        return current_lakh + 20
    return current_lakh + 25


def mode_cfg(mode):
    return MODES[mode]


def team_squad(con, code, team_id, mode):
    rows = con.execute(
        "SELECT * FROM players WHERE room_code=? AND status='sold' AND sold_team_id=?",
        (code, team_id),
    ).fetchall()
    purse = mode_cfg(mode)["purse_cr"] * 100
    spent = sum(r["sold_price_lakh"] or 0 for r in rows)
    overseas = sum(1 for r in rows if r["country"] != "India")
    return {
        "count": len(rows),
        "overseas": overseas,
        "indians": len(rows) - overseas,
        "spent_lakh": spent,
        "remaining_lakh": purse - spent,
        "players": [with_stats(r) for r in rows],
    }


def _next_upcoming(con, code, mode):
    sets = mode_cfg(mode)["sets"]
    placeholders = ",".join("?" for _ in sets)
    return con.execute(
        f"SELECT * FROM players WHERE room_code=? AND status='upcoming'"
        f" AND set_name IN ({placeholders}) ORDER BY order_index LIMIT 1",
        [code] + sets).fetchone()


def _start_player(con, code, player, now):
    con.execute(
        """UPDATE auction SET status='bidding', current_player_id=?,
           current_bid_lakh=NULL, current_bidder_id=NULL, current_team_id=NULL,
           bid_deadline=?, result_until=NULL, last_player_id=NULL, last_result=NULL
           WHERE room_code=?""",
        (player["id"], now + BID_WINDOW, code),
    )
    emit(con, code, "player_up", {
        "player_id": player["id"], "player_name": player["name"],
        "set": player["set_name"], "base_lakh": player["base_lakh"],
        "country": player["country"], "role": player["role"],
    })


def _finalize_current(con, code, now, forced_unsold=False):
    """Hammer falls: sold to highest bidder, or unsold."""
    a = con.execute("SELECT * FROM auction WHERE room_code=?", (code,)).fetchone()
    if not a["current_player_id"]:
        return
    p = con.execute("SELECT * FROM players WHERE id=? AND room_code=?",
                    (a["current_player_id"], code)).fetchone()
    if a["current_bid_lakh"] and not forced_unsold:
        con.execute(
            """UPDATE players SET status='sold', sold_price_lakh=?,
               sold_team_id=?, sold_bidder_id=? WHERE id=?""",
            (a["current_bid_lakh"], a["current_team_id"], a["current_bidder_id"], p["id"]),
        )
        team_name = TEAMS[a["current_team_id"]][1]
        bidder = con.execute("SELECT name FROM bidders WHERE id=? AND room_code=?",
                             (a["current_bidder_id"], code)).fetchone()
        emit(con, code, "sold", {
            "player_id": p["id"], "player_name": p["name"],
            "team_id": a["current_team_id"], "team_name": team_name,
            "bidder_name": bidder["name"] if bidder else "",
            "price_lakh": a["current_bid_lakh"],
        })
        result = "sold"
    else:
        con.execute("UPDATE players SET status='unsold' WHERE id=?", (p["id"],))
        emit(con, code, "unsold", {"player_id": p["id"], "player_name": p["name"]})
        result = "unsold"
    con.execute(
        """UPDATE auction SET status='result', result_until=?,
           last_player_id=?, last_result=?,
           current_player_id=NULL, current_bid_lakh=NULL,
           current_bidder_id=NULL, current_team_id=NULL, bid_deadline=NULL
           WHERE room_code=?""",
        (now + RESULT_SECS, p["id"], result, code),
    )


def tick(con, code, now):
    """Advance timers. Called on every state read / mutation."""
    a = con.execute("SELECT * FROM auction WHERE room_code=?", (code,)).fetchone()
    if a["status"] == "bidding":
        if a["current_player_id"] and now >= (a["bid_deadline"] or 0):
            _finalize_current(con, code, now)
            con.commit()
    a = con.execute("SELECT * FROM auction WHERE room_code=?", (code,)).fetchone()
    if a["status"] == "result" and now >= (a["result_until"] or 0):
        nxt = _next_upcoming(con, code, a["mode"])
        if nxt:
            _start_player(con, code, nxt, now)
        else:
            con.execute("UPDATE auction SET status='done', last_player_id=NULL,"
                        " last_result=NULL WHERE room_code=?", (code,))
            emit(con, code, "auction_done", {"mode": a["mode"]})
        con.commit()


def can_bid(con, code, a, bidder, amount):
    """Validate a bid of `amount` lakh by bidder. Returns (ok, reason)."""
    mode = mode_cfg(a["mode"])
    team_id = bidder["team_id"]
    p = con.execute("SELECT * FROM players WHERE id=? AND room_code=?",
                    (a["current_player_id"], code)).fetchone()
    squad = team_squad(con, code, team_id, a["mode"])
    if squad["count"] >= mode["squad_size"]:
        return False, "Your squad is full."
    overseas_after = squad["overseas"] + (1 if p["country"] != "India" else 0)
    if overseas_after > mode["max_overseas"]:
        return False, f"Overseas limit reached (max {mode['max_overseas']})."
    slots_left_after = mode["squad_size"] - (squad["count"] + 1)
    need_overseas = max(0, mode["min_overseas"] - overseas_after)
    if slots_left_after < need_overseas:
        return False, f"You still need {need_overseas} more overseas player(s)."
    indians_after = squad["indians"] + (1 if p["country"] == "India" else 0)
    if indians_after > mode["squad_size"] - mode["min_overseas"]:
        return False, "You must leave room for overseas picks."
    if squad["remaining_lakh"] < amount:
        return False, "Not enough purse left."
    if squad["remaining_lakh"] - amount < MIN_BASE_LAKH * slots_left_after:
        return False, "Bid would leave you unable to fill your squad."
    return True, ""


def room_or_404(con, code):
    room = get_room(con, code)
    if not room:
        return None, (jsonify({"ok": False, "error": "Room not found. Check the code."}), 404)
    return room, None


# ------------------------------------------------------------------- routes
@app.get("/")
def index():
    return send_from_directory(STATIC_DIR, "index.html")


@app.get("/<path:filename>")
def static_files(filename):
    return send_from_directory(STATIC_DIR, filename)


@app.post("/api/rooms")
def api_create_room():
    """Create a room. Body: {name, auth}. Returns {code, host_token}.
    The creator becomes the room owner — only they can start the match."""
    body = request.get_json(force=True)
    name = (body.get("name") or "").strip()[:30]
    if not name:
        return jsonify({"ok": False, "error": "Please enter your name."}), 400
    with lock:
        con = db()
        try:
            u = auth_user(con, body.get("auth"))
            if not u:
                return jsonify({"ok": False, "error": "Please log in first."}), 401
            code = new_room_code(con)
            host_token = secrets.token_hex(8)
            con.execute("INSERT INTO rooms(code, host_token, created_at, owner_user_id)"
                        " VALUES (?,?,?,?)",
                        (code, host_token, time.time(), u["id"]))
            con.execute("INSERT INTO auction(room_code, status) VALUES (?, 'lobby')",
                        (code,))
            seed_room_players(con, code)
            emit(con, code, "room_created", {"by": name})
            con.commit()
            return jsonify({"ok": True, "code": code, "host_token": host_token})
        finally:
            con.close()


EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
OTP_TTL = 600        # codes expire after 10 minutes
OTP_COOLDOWN = 60    # seconds between code requests for the same email
OTP_MAX_ATTEMPTS = 5  # wrong guesses before a code is voided


def _mail_cfg():
    """Gmail SMTP credentials from env. Empty strings mean not configured."""
    return (os.environ.get("MAIL_USER", "").strip(),
            os.environ.get("MAIL_APP_PASSWORD", "").strip())


def send_otp_email(to_email, code):
    """Email the OTP via Gmail SMTP. Returns True on success."""
    user, pw = _mail_cfg()
    if not user or not pw:
        return False
    msg = EmailMessage()
    msg["From"] = user
    msg["To"] = to_email
    msg["Subject"] = "Your IPL Auction Arena login code"
    msg.set_content(
        f"Your one-time login code is: {code}\n\n"
        "It expires in 10 minutes. If you didn't request this, just ignore this email.\n"
        "— IPL Auction Arena")
    ctx = ssl.create_default_context()
    with smtplib.SMTP("smtp.gmail.com", 587, timeout=20) as s:
        s.starttls(context=ctx)
        s.login(user, pw)
        s.send_message(msg)
    return True


def _hash_code(email, code):
    return hashlib.sha256(f"{email.lower()}:{code}".encode()).hexdigest()


@app.post("/api/auth/request_otp")
def api_request_otp():
    """Send a 6-digit code to an email address. Body: {email}."""
    body = request.get_json(force=True)
    email = (body.get("email") or "").strip().lower()
    if not EMAIL_RE.match(email):
        return jsonify({"ok": False, "error": "Enter a valid email address."}), 400
    with lock:
        con = db()
        try:
            now = time.time()
            last = con.execute(
                "SELECT created_at FROM otp_codes WHERE email=? AND used=0"
                " ORDER BY id DESC LIMIT 1", (email,)).fetchone()
            if last and now - last["created_at"] < OTP_COOLDOWN:
                wait = int(OTP_COOLDOWN - (now - last["created_at"]))
                return jsonify({"ok": False,
                                "error": f"Code already sent. Try again in {wait}s."}), 429
            code = f"{secrets.randbelow(900000) + 100000}"
            # void older pending codes for this email
            con.execute("UPDATE otp_codes SET used=1 WHERE email=? AND used=0",
                        (email,))
            con.execute(
                "INSERT INTO otp_codes(email,code_hash,created_at,expires_at)"
                " VALUES (?,?,?,?)",
                (email, _hash_code(email, code), now, now + OTP_TTL))
            con.commit()
            try:
                ok = send_otp_email(email, code)
            except Exception:
                ok = False
            if not ok:
                # fail closed: void the code, never reveal it
                con.execute("UPDATE otp_codes SET used=1 WHERE email=? AND used=0",
                            (email,))
                con.commit()
                return jsonify({"ok": False,
                                "error": "Couldn't send the code. The server's email"
                                         " is not set up yet — ask the host to add it."}), 503
            return jsonify({"ok": True})
        finally:
            con.close()


@app.post("/api/auth/verify_otp")
def api_verify_otp():
    """Verify a code. Body: {email, code, name?}. New emails need a name to
    finish registering; existing accounts just log in. Returns {token, name}."""
    body = request.get_json(force=True)
    email = (body.get("email") or "").strip().lower()
    code = (body.get("code") or "").strip()
    name = (body.get("name") or "").strip()[:30]
    if not EMAIL_RE.match(email) or not code:
        return jsonify({"ok": False, "error": "Enter your email and the code."}), 400
    with lock:
        con = db()
        try:
            now = time.time()
            row = con.execute(
                "SELECT * FROM otp_codes WHERE email=? AND used=0"
                " ORDER BY id DESC LIMIT 1", (email,)).fetchone()
            if not row or now > row["expires_at"]:
                return jsonify({"ok": False,
                                "error": "That code expired. Request a new one."}), 401
            if row["attempts"] >= OTP_MAX_ATTEMPTS:
                con.execute("UPDATE otp_codes SET used=1 WHERE id=?", (row["id"],))
                con.commit()
                return jsonify({"ok": False,
                                "error": "Too many wrong tries. Request a new code."}), 401
            if not hmac.compare_digest(row["code_hash"], _hash_code(email, code)):
                con.execute("UPDATE otp_codes SET attempts=attempts+1 WHERE id=?",
                            (row["id"],))
                con.commit()
                return jsonify({"ok": False, "error": "Wrong code. Try again."}), 401
            con.execute("UPDATE otp_codes SET used=1 WHERE id=?", (row["id"],))
            u = con.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
            if not u:
                if not name:
                    return jsonify({"ok": False,
                                    "error": "Enter your name to finish registering."}), 400
                cur = con.execute(
                    "INSERT INTO users(name,email,created_at) VALUES (?,?,?)",
                    (name, email, now))
                user_id, name = cur.lastrowid, name
            else:
                user_id, name = u["id"], u["name"]
            token = new_session(con, user_id)
            con.commit()
            return jsonify({"ok": True, "token": token, "name": name})
        finally:
            con.close()


@app.post("/api/auth/logout")
def api_logout():
    body = request.get_json(force=True)
    with lock:
        con = db()
        try:
            con.execute("DELETE FROM sessions WHERE token=?", (body.get("token"),))
            con.commit()
            return jsonify({"ok": True})
        finally:
            con.close()


@app.get("/api/r/<code>/state")
def api_state(code):
    token = request.args.get("token", "")
    auth = request.args.get("auth", "")
    since = int(request.args.get("since", "0") or 0)
    with lock:
        con = db()
        try:
            room, err = room_or_404(con, code)
            if err:
                return err
            code = room["code"]
            now = time.time()
            tick(con, code, now)
            a = con.execute("SELECT * FROM auction WHERE room_code=?", (code,)).fetchone()
            u = auth_user(con, auth)
            me = None
            if token:
                r = con.execute("SELECT * FROM bidders WHERE token=? AND room_code=?",
                                (token, code)).fetchone()
                if r:
                    me = {"id": r["id"], "name": r["name"], "team_id": r["team_id"],
                          "is_host": (a["host_token"] == token)}
            teams = []
            for tid, (short, name, color, tcolor) in enumerate(TEAMS):
                b = con.execute("SELECT * FROM bidders WHERE room_code=? AND team_id=?",
                                (code, tid)).fetchone()
                sq = team_squad(con, code, tid, a["mode"]) if a["mode"] else None
                teams.append({
                    "id": tid, "short": short, "name": name, "color": color,
                    "text_color": tcolor, "occupied_by": b["name"] if b else None,
                    "squad": sq,
                })
            sets = []
            if a["mode"]:
                for s in mode_cfg(a["mode"])["sets"]:
                    rows = con.execute(
                        "SELECT * FROM players WHERE room_code=? AND set_name=?"
                        " ORDER BY order_index", (code, s)
                    ).fetchall()
                    sets.append({"name": s, "players": [with_stats(r) for r in rows]})
            cur = None
            if a["current_player_id"]:
                p = con.execute("SELECT * FROM players WHERE id=? AND room_code=?",
                                (a["current_player_id"], code)).fetchone()
                tb = None
                if a["current_team_id"] is not None:
                    t = TEAMS[a["current_team_id"]]
                    tb = {"id": a["current_team_id"], "short": t[0], "name": t[1]}
                bb = None
                if a["current_bidder_id"]:
                    bb = con.execute("SELECT name FROM bidders WHERE id=? AND room_code=?",
                                     (a["current_bidder_id"], code)).fetchone()
                cur = {
                    "player": with_stats(p),
                    "bid_lakh": a["current_bid_lakh"],
                    "team": tb,
                    "bidder_name": bb["name"] if bb else None,
                    "deadline": a["bid_deadline"],
                    "next_bid_lakh": next_bid_amount(a["current_bid_lakh"], p["base_lakh"]),
                }
            last = None
            if a["last_player_id"]:
                p = con.execute("SELECT * FROM players WHERE id=? AND room_code=?",
                                (a["last_player_id"], code)).fetchone()
                last = {"player": with_stats(p), "result": a["last_result"]}
            evs = con.execute("SELECT seq, ts, type, data FROM events"
                              " WHERE room_code=? AND seq > ? ORDER BY seq",
                              (code, since)).fetchall()
            events = [{"seq": e["seq"], "ts": e["ts"], "type": e["type"],
                       "data": json.loads(e["data"])} for e in evs]
            max_seq = con.execute("SELECT MAX(seq) AS m FROM events WHERE room_code=?",
                                  (code,)).fetchone()["m"] or 0
            bidders = [{"name": b["name"], "team_id": b["team_id"]}
                       for b in con.execute("SELECT name, team_id FROM bidders"
                                            " WHERE room_code=? ORDER BY joined_at", (code,))]
            owner_id = room_owner_id(con, code)
            owner_row = con.execute("SELECT name, team_id FROM bidders"
                                    " WHERE room_code=? AND user_id=?",
                                    (code, owner_id)).fetchone()
            return jsonify({
                "now": now,
                "seq": max_seq,
                "room": {"code": code, "bidder_count": len(bidders),
                         "min_bidders": MIN_BIDDERS,
                         "is_owner": bool(me and u and u["id"] == owner_id),
                         "owner_name": owner_row["name"] if owner_row else None},
                "user": {"name": u["name"]} if u else None,
                "auction": {"mode": a["mode"], "status": a["status"],
                            "mode_cfg": mode_cfg(a["mode"]) if a["mode"] else None,
                            "result_until": a["result_until"]},
                "me": me,
                "teams": teams,
                "bidders": bidders,
                "sets": sets,
                "current": cur,
                "last": last,
                "events": events,
                "modes": {k: {"label": v["label"], "purse_cr": v["purse_cr"],
                              "squad_size": v["squad_size"],
                              "max_overseas": v["max_overseas"],
                              "min_overseas": v["min_overseas"],
                              "blurb": v["blurb"]} for k, v in MODES.items()},
            })
        finally:
            con.close()


@app.post("/api/r/<code>/join")
def api_join(code):
    body = request.get_json(force=True)
    name = (body.get("name") or "").strip()[:30]
    team_id = body.get("team_id")
    if not name:
        return jsonify({"ok": False, "error": "Please enter your name."}), 400
    if not isinstance(team_id, int) or not (0 <= team_id < len(TEAMS)):
        return jsonify({"ok": False, "error": "Pick a team."}), 400
    with lock:
        con = db()
        try:
            room, err = room_or_404(con, code)
            if err:
                return err
            code = room["code"]
            u = auth_user(con, body.get("auth"))
            if not u:
                return jsonify({"ok": False,
                                "error": "Please log in first."}), 401
            if con.execute("SELECT 1 FROM bidders WHERE room_code=? AND team_id=?",
                           (code, team_id)).fetchone():
                return jsonify({"ok": False,
                                "error": f"{TEAMS[team_id][1]} is already taken."}), 409
            if con.execute("SELECT 1 FROM bidders WHERE room_code=? AND user_id=?",
                           (code, u["id"])).fetchone():
                return jsonify({"ok": False,
                                "error": "You've already joined this room."}), 409
            token = secrets.token_hex(8)
            con.execute("INSERT INTO bidders(room_code,name,team_id,token,user_id,joined_at)"
                        " VALUES (?,?,?,?,?,?)",
                        (code, name, team_id, token, u["id"], time.time()))
            emit(con, code, "team_joined", {"name": name, "team_id": team_id,
                                            "team_name": TEAMS[team_id][1]})
            con.commit()
            return jsonify({"ok": True, "token": token, "name": name, "team_id": team_id})
        finally:
            con.close()


@app.post("/api/r/<code>/leave")
def api_leave(code):
    body = request.get_json(force=True)
    with lock:
        con = db()
        try:
            room, err = room_or_404(con, code)
            if err:
                return err
            code = room["code"]
            b = con.execute("SELECT * FROM bidders WHERE token=? AND room_code=?",
                            (body.get("token"), code)).fetchone()
            if b:
                was_owner = (b["user_id"] is not None
                             and b["user_id"] == room_owner_id(con, code))
                con.execute("DELETE FROM bidders WHERE id=?", (b["id"],))
                if was_owner:
                    # hand ownership to the earliest remaining bidder
                    nxt = con.execute(
                        "SELECT user_id FROM bidders WHERE room_code=?"
                        " AND user_id IS NOT NULL ORDER BY joined_at LIMIT 1",
                        (code,)).fetchone()
                    if nxt:
                        con.execute("UPDATE rooms SET owner_user_id=? WHERE code=?",
                                    (nxt["user_id"], code))
                emit(con, code, "team_left", {"name": b["name"], "team_id": b["team_id"]})
                con.commit()
            return jsonify({"ok": True})
        finally:
            con.close()


def _host(con, code, token):
    a = con.execute("SELECT * FROM auction WHERE room_code=?", (code,)).fetchone()
    b = con.execute("SELECT * FROM bidders WHERE token=? AND room_code=?",
                    (token, code)).fetchone()
    if not b:
        return None, (jsonify({"ok": False, "error": "Join first."}), 401)
    if a["host_token"] != token:
        return None, (jsonify({"ok": False, "error": "Only the host controls the auction."}), 403)
    return (a, b), None


@app.post("/api/r/<code>/start")
def api_start(code):
    body = request.get_json(force=True)
    mode = body.get("mode")
    if mode not in MODES:
        return jsonify({"ok": False, "error": "Pick a valid mode."}), 400
    with lock:
        con = db()
        try:
            room, err = room_or_404(con, code)
            if err:
                return err
            code = room["code"]
            b = con.execute("SELECT * FROM bidders WHERE token=? AND room_code=?",
                            (body.get("token"), code)).fetchone()
            if not b:
                return jsonify({"ok": False, "error": "Join first."}), 401
            # only the room owner can start the match
            if b["user_id"] != room_owner_id(con, code):
                return jsonify({"ok": False,
                                "error": "Only the room owner can start the match."}), 403
            # need a minimum number of bidders in the lobby
            n = con.execute("SELECT COUNT(*) AS c FROM bidders WHERE room_code=?",
                            (code,)).fetchone()["c"]
            if n < MIN_BIDDERS:
                return jsonify({"ok": False,
                                "error": f"Need at least {MIN_BIDDERS} bidders to start"
                                         f" — {n} joined so far."}), 400
            now = time.time()
            con.execute("UPDATE auction SET mode=?, status='lobby', host_token=?"
                        " WHERE room_code=?", (mode, b["token"], code))
            nxt = _next_upcoming(con, code, mode)
            _start_player(con, code, nxt, now)
            emit(con, code, "auction_started", {"mode": mode, "label": MODES[mode]["label"],
                                                "host": b["name"]})
            con.commit()
            return jsonify({"ok": True})
        finally:
            con.close()


@app.post("/api/r/<code>/bid")
def api_bid(code):
    body = request.get_json(force=True)
    with lock:
        con = db()
        try:
            room, err = room_or_404(con, code)
            if err:
                return err
            code = room["code"]
            now = time.time()
            tick(con, code, now)
            a = con.execute("SELECT * FROM auction WHERE room_code=?", (code,)).fetchone()
            if a["status"] != "bidding" or not a["current_player_id"]:
                return jsonify({"ok": False, "error": "No live bidding right now."}), 400
            bidder = con.execute("SELECT * FROM bidders WHERE token=? AND room_code=?",
                                 (body.get("token"), code)).fetchone()
            if not bidder:
                return jsonify({"ok": False, "error": "Join first."}), 401
            p = con.execute("SELECT * FROM players WHERE id=? AND room_code=?",
                            (a["current_player_id"], code)).fetchone()
            amount = next_bid_amount(a["current_bid_lakh"], p["base_lakh"])
            if a["current_bidder_id"] == bidder["id"]:
                return jsonify({"ok": False, "error": "You already hold the bid."}), 400
            ok, reason = can_bid(con, code, a, bidder, amount)
            if not ok:
                return jsonify({"ok": False, "error": reason}), 400
            deadline = max(a["bid_deadline"] or 0, now + BID_EXTEND)
            con.execute(
                """UPDATE auction SET current_bid_lakh=?, current_bidder_id=?,
                   current_team_id=?, bid_deadline=? WHERE room_code=?""",
                (amount, bidder["id"], bidder["team_id"], deadline, code),
            )
            emit(con, code, "bid", {
                "player_id": p["id"], "player_name": p["name"],
                "team_id": bidder["team_id"], "team_name": TEAMS[bidder["team_id"]][1],
                "bidder_name": bidder["name"], "amount_lakh": amount,
            })
            con.commit()
            return jsonify({"ok": True, "amount_lakh": amount})
        finally:
            con.close()


@app.post("/api/r/<code>/hammer")
def api_hammer(code):
    body = request.get_json(force=True)
    with lock:
        con = db()
        try:
            room, err = room_or_404(con, code)
            if err:
                return err
            code = room["code"]
            res, err = _host(con, code, body.get("token"))
            if err:
                return err
            now = time.time()
            tick(con, code, now)
            a = con.execute("SELECT * FROM auction WHERE room_code=?", (code,)).fetchone()
            if a["status"] != "bidding":
                return jsonify({"ok": False, "error": "Nothing to hammer."}), 400
            _finalize_current(con, code, now)
            con.commit()
            return jsonify({"ok": True})
        finally:
            con.close()


@app.post("/api/r/<code>/mark_unsold")
def api_mark_unsold(code):
    body = request.get_json(force=True)
    with lock:
        con = db()
        try:
            room, err = room_or_404(con, code)
            if err:
                return err
            code = room["code"]
            res, err = _host(con, code, body.get("token"))
            if err:
                return err
            now = time.time()
            tick(con, code, now)
            a = con.execute("SELECT * FROM auction WHERE room_code=?", (code,)).fetchone()
            if a["status"] != "bidding":
                return jsonify({"ok": False, "error": "Nothing live."}), 400
            _finalize_current(con, code, now, forced_unsold=True)
            con.commit()
            return jsonify({"ok": True})
        finally:
            con.close()


@app.post("/api/r/<code>/next")
def api_next(code):
    body = request.get_json(force=True)
    with lock:
        con = db()
        try:
            room, err = room_or_404(con, code)
            if err:
                return err
            code = room["code"]
            res, err = _host(con, code, body.get("token"))
            if err:
                return err
            now = time.time()
            tick(con, code, now)
            a = con.execute("SELECT * FROM auction WHERE room_code=?", (code,)).fetchone()
            if a["status"] == "bidding":
                _finalize_current(con, code, now)
                con.commit()
                return jsonify({"ok": True})
            if a["status"] == "result":
                con.execute("UPDATE auction SET result_until=0 WHERE room_code=?", (code,))
                con.commit()
                return jsonify({"ok": True})
            return jsonify({"ok": False, "error": "Nothing to advance."}), 400
        finally:
            con.close()


@app.post("/api/r/<code>/reset")
def api_reset(code):
    body = request.get_json(force=True)
    with lock:
        con = db()
        try:
            room, err = room_or_404(con, code)
            if err:
                return err
            code = room["code"]
            res, err = _host(con, code, body.get("token"))
            if err:
                return err
            con.execute("""UPDATE players SET status='upcoming', sold_price_lakh=NULL,
                           sold_team_id=NULL, sold_bidder_id=NULL WHERE room_code=?""",
                        (code,))
            con.execute("DELETE FROM events WHERE room_code=?", (code,))
            con.execute("""UPDATE auction SET mode=NULL, status='lobby', host_token=NULL,
                           current_player_id=NULL, current_bid_lakh=NULL,
                           current_bidder_id=NULL, current_team_id=NULL,
                           bid_deadline=NULL, result_until=NULL,
                           last_player_id=NULL, last_result=NULL
                           WHERE room_code=?""", (code,))
            con.commit()
            return jsonify({"ok": True})
        finally:
            con.close()


@app.post("/api/r/<code>/player_image")
def api_player_image(code):
    body = request.get_json(force=True)
    with lock:
        con = db()
        try:
            room, err = room_or_404(con, code)
            if err:
                return err
            code = room["code"]
            res, err = _host(con, code, body.get("token"))
            if err:
                return err
            con.execute("UPDATE players SET img=? WHERE id=? AND room_code=?",
                        ((body.get("img_url") or "").strip()[:500] or None,
                         body.get("player_id"), code))
            con.commit()
            return jsonify({"ok": True})
        finally:
            con.close()


init_db()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    print(f"IPL Auction Arena on http://0.0.0.0:{port}")
    app.run(host="0.0.0.0", port=port, threaded=True)
