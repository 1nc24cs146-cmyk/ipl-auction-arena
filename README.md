# 🏏 IPL Auction Arena

A full-stack, real-time cricket auction game. Create a **room** and share
the 6-letter room code — friends join from their own browsers, each picks
one of the 10 IPL franchises (one bidder per team — a taken team can't be
picked again), and bid live for players to build their own squad. Every
room runs its own separate auction.

## Run it

```bash
cd ~/workspace/cricket-auction
chmod +x run.sh
./run.sh
```

Open **http://localhost:5000** in your browser.
Friends on the same Wi-Fi join via `http://<your-computer-ip>:5000`.

Player data, bids, squads and auction state are stored in `auction.db`
(SQLite) — everything persists in the backend.

## Deploy it (so friends can join from anywhere)

The app is ready to deploy as a Python web service (tested with
gunicorn). Easiest free route — **Render**:

1. Put this folder in a GitHub repo (`.gitignore` already excludes
   `venv/`, `__pycache__/` and `auction.db`).
2. Go to [render.com](https://render.com) → **New → Web Service** →
   connect your repo. (Or use the `render.yaml` in this folder as a
   Blueprint.)
3. Settings: **Runtime** Python, **Build command**
   `pip install -r requirements.txt`, **Start command**
   `gunicorn app:app --bind 0.0.0.0:$PORT --workers 1 --threads 8 --timeout 120`.
4. Deploy — you'll get a public URL like
   `https://ipl-auction-arena.onrender.com`. Share it with friends.

> ⚠️ One caveat: on free hosting the SQLite database resets when the
> service restarts or sleeps, so rooms only last for your game session.
> For a game night that's all you need — everyone just creates a fresh
> room and plays.

Railway and Fly.io work too — same build/start commands.

## The 3 modes

| Mode | Purse | Squad | Overseas | Player pool |
|------|-------|-------|----------|-------------|
| **Mega Auction** | ₹120 Cr | 11 players | min 4, max 8 | All 125 players, 8 sets |
| **Mini Auction** | ₹60 Cr | 8 players | min 2, max 4 | Marquee + all capped sets |
| **Quick Auction** | ₹30 Cr | 6 players | max 3 | Marquee + batters, all-rounders, keepers |

## How it plays

1. **Log in or register** (name + password) on the first page.
2. **Create a room** (you get a 6-letter code — you become the room owner)
   or **join** with a code. Share the code with friends.
3. Enter your name, pick your favourite IPL team (taken teams are locked —
   one bidder per team). Everyone waits in the **lobby**, which shows every
   team with its bidder's name.
4. **Only the room owner** can start the match, and only once **at least
   5 bidders** have joined the lobby.
5. The owner picks an auction mode and becomes the **host**.
6. Players come up **set by set**, exactly like the real IPL auction:
   Marquee Set 1 → Marquee Set 2 → Capped Batters → All-Rounders →
   Wicket-Keepers → Fast Bowlers → Spinners → Uncapped Stars.
7. Hit **BID** (or press `B`) — bids rise by official IPL increments
   (₹5L under ₹1 Cr, ₹10L to ₹2 Cr, ₹20L to ₹5 Cr, ₹25L above).
8. The 🎙️ **female auctioneer voice** announces every bid
   ("*Mumbai Indians bid 2 crore 20 lakh for Rishabh Pant*") and
   congratulates the winning team on every sale.
9. The hammer falls automatically when the timer runs out, or the host
   can hammer / mark unsold / skip ahead.
10. Track everything in the **Upcoming / Sold / Unsold** tabs and watch
    every team's purse and squad build in real time.

### Squad rules (enforced by the backend)

- Can't exceed your squad size or overseas cap.
- Must still be able to meet the overseas minimum with remaining slots.
- A bid can't leave you unable to fill the rest of your squad at base price.

### Extras

- Host can attach a real photo URL to any player card (host-only
  "set photo URL" link on the live player card). Cards without a photo
  show a stylish initials avatar.
- Voice toggle in the top bar; every announcement also appears as a caption.

## Tech

Python + Flask + SQLite backend, vanilla JS frontend, Web Speech API
for the auctioneer voice. No build step, no accounts — just open and play.
