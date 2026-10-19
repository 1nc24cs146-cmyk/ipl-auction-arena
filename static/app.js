/* IPL Auction Arena - frontend (rooms edition) */
const $ = (id) => document.getElementById(id);
const store = {
  get auth() { return localStorage.getItem("auc_auth") || ""; },
  set auth(v) { v ? localStorage.setItem("auc_auth", v) : localStorage.removeItem("auc_auth"); },
  get roomCode() { return localStorage.getItem("auc_room") || ""; },
  set roomCode(v) { v ? localStorage.setItem("auc_room", v) : localStorage.removeItem("auc_room"); },
  get token() {
    const c = store.roomCode;
    return c ? (localStorage.getItem("auc_token_" + c) || "") : "";
  },
  set token(v) {
    const c = store.roomCode;
    if (!c) return;
    v ? localStorage.setItem("auc_token_" + c, v) : localStorage.removeItem("auc_token_" + c);
  },
};
const R = (path) => `/api/r/${store.roomCode}${path}`;

let S = null;              // latest full state
let lastSeq = 0;           // events consumed
let lastSpokenSeq = 0;     // events voiced
let voiceOn = true;
let pickedTeam = null;
let activeTab = "upcoming";
let femaleVoice = null;

/* ---------------- helpers ---------------- */
async function api(path, method = "GET", body) {
  const r = await fetch(path, {
    method, headers: { "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  });
  return r.json();
}
function fmtLakh(l) {
  if (l == null) return "—";
  if (l >= 100) {
    const cr = (l / 100).toFixed(2).replace(/\.00$/, "").replace(/(\.\d)0$/, "$1");
    return `₹${cr} Cr`;
  }
  return `₹${l} L`;
}
function speakLakh(l) {
  const cr = Math.floor(l / 100), rem = l % 100;
  const parts = [];
  if (cr) parts.push(`${cr} crore`);
  if (rem) parts.push(`${rem} lakh`);
  return parts.join(" ") || "zero";
}
function initials(name) {
  return name.split(" ").map(w => w[0]).slice(0, 2).join("").toUpperCase();
}
function fmtNum(n) {
  return n == null ? "–" : n.toLocaleString("en-IN");
}
function statsLine(p) {
  const s = p.stats;
  if (!s || (s.mat == null && s.runs == null && s.wkts == null)) return "";
  return `<span class="st-num">🏏 ${fmtNum(s.mat)}</span> mat · <span class="st-num">🏃 ${fmtNum(s.runs)}</span> runs · <span class="st-num">🎯 ${fmtNum(s.wkts)}</span> wkts`;
}
function esc(s) { return String(s).replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c])); }
function avatarHTML(p, cls) {
  const inner = p.img
    ? `<span>${initials(p.name)}</span><img src="${esc(p.img)}" onerror="this.remove()" alt="">`
    : `<span>${initials(p.name)}</span>`;
  return `<div class="${cls}">${inner}</div>`;
}
const ROLE = { BAT:"Batter", AR:"All-Rounder", WK:"Wicket-Keeper", BOWL:"Fast Bowler", SPIN:"Spinner" };
const FLAG = { "India":"🇮🇳","England":"🏴󐁧󐁢󐁥󐁮󐁧󐁿","Australia":"🇦🇺","South Africa":"🇿🇦","New Zealand":"🇳🇿",
  "West Indies":"🏝️","Afghanistan":"🇦🇫","Sri Lanka":"🇱🇰","Bangladesh":"🇧🇩","Zimbabwe":"🇿🇼" };

/* ---------------- voice (female auctioneer) ---------------- */
function pickFemaleVoice() {
  const vs = speechSynthesis.getVoices();
  femaleVoice =
    vs.find(v => /female/i.test(v.name)) ||
    vs.find(v => /samantha|zira|veena|karen|moira|tessa|fiona|google uk english female|neerja/i.test(v.name)) ||
    vs.find(v => v.lang && v.lang.toLowerCase().startsWith("en")) || null;
}
if ("speechSynthesis" in window) {
  pickFemaleVoice();
  speechSynthesis.onvoiceschanged = pickFemaleVoice;
}
function speak(text) {
  if (!voiceOn || !("speechSynthesis" in window)) return;
  speechSynthesis.cancel();
  const u = new SpeechSynthesisUtterance(text);
  if (femaleVoice) u.voice = femaleVoice;
  u.rate = 1.02; u.pitch = 1.05;
  speechSynthesis.speak(u);
  $("captionBar").classList.remove("hidden");
  $("captionText").textContent = text;
}
function handleEvent(e) {
  const d = e.data;
  if (e.type === "bid") {
    speak(`${d.team_name} bid ${speakLakh(d.amount_lakh)} for ${d.player_name}.`);
  } else if (e.type === "sold") {
    speak(`Congratulations ${d.team_name}! ${d.player_name} sold for ${speakLakh(d.price_lakh)}.`);
  } else if (e.type === "unsold") {
    speak(`${d.player_name} goes unsold.`);
  } else if (e.type === "player_up") {
    speak(`${d.player_name} is next, at a base price of ${speakLakh(d.base_lakh)}.`);
  } else if (e.type === "auction_started") {
    speak(`The ${d.label} has begun. Good luck to all teams.`);
  }
}

/* ---------------- polling ---------------- */
async function poll() {
  if (!store.auth) { showView("auth"); return; }
  if (!store.roomCode) { showView("rooms"); renderUserBadge(); return; }
  try {
    const st = await api(`${R("/state")}?token=${store.token}&auth=${store.auth}&since=${lastSeq}`);
    if (st && st.ok === false) {
      // room gone or invalid
      $("joinRoomMsg").textContent = st.error || "Room not found.";
      leaveRoomLocal();
      return;
    }
    if (st && st.seq !== undefined) {
      st.clientNow = Date.now() / 1000; // when this snapshot arrived
      S = st;
      for (const e of st.events) {
        if (e.seq > lastSpokenSeq) { handleEvent(e); lastSpokenSeq = e.seq; }
      }
      lastSeq = st.seq;
      render();
    }
  } catch (e) { /* retry next tick */ }
}
setInterval(poll, 1500);
setInterval(updateTimer, 400);

/* ---------------- views ---------------- */
function showView(name) {
  ["auth", "rooms", "lobby", "auction"].forEach(v => $("view-" + v).classList.toggle("hidden", v !== name));
}
function renderUserBadge() {
  const u = S && S.user ? S.user.name : null;
  const badge = $("userBadge"), btn = $("logoutBtn");
  if (u) {
    badge.textContent = "👤 " + u;
    badge.classList.remove("hidden");
    btn.classList.remove("hidden");
  } else {
    badge.classList.add("hidden");
    btn.classList.add("hidden");
  }
}
function leaveRoomLocal() {
  store.token = "";
  store.roomCode = "";
  S = null; lastSeq = 0; lastSpokenSeq = 0; pickedTeam = null;
  showView("rooms");
}
function logoutLocal() {
  store.auth = "";
  leaveRoomLocal();
  showView("auth");
}

/* ---------------- render ---------------- */
function render() {
  if (!store.auth) { showView("auth"); return; }
  renderUserBadge();
  if (!store.roomCode) { showView("rooms"); return; }
  const rb = $("roomBadge");
  rb.textContent = "Room " + store.roomCode;
  rb.classList.remove("hidden");
  const a = S.auction;
  const live = a.mode && a.status !== "lobby";
  if (live) { showView("auction"); }
  else { showView("lobby"); }
  if (!live) { renderLobby(); return; }
  $("modeBadge").textContent = a.mode_cfg.label;
  $("modeBadge").classList.remove("hidden");
  renderStage(); renderSide(); renderLists(); renderOverlay();
}

function renderLobby() {
  $("roomCodeBig").textContent = store.roomCode;
  const members = S.bidders || [];
  $("roomMembers").innerHTML = members.length
    ? `<div class="room-code-label" style="margin-top:10px">In this room (${members.length}):</div>` +
      members.map(m => {
        const t = S.teams[m.team_id];
        return `<span class="member-chip" style="border-color:${t.color}">${esc(m.name)} · ${t.short}</span>`;
      }).join(" ")
    : `<div style="color:var(--mut);font-size:13px;margin-top:10px">No bidders yet — pick your team below.</div>`;
  // team grid
  const g = $("teamGrid"); g.innerHTML = "";
  S.teams.forEach(t => {
    const d = document.createElement("div");
    d.className = "team-pick" + (t.occupied_by ? " taken" : "") + (pickedTeam === t.id ? " selected" : "");
    d.innerHTML = `<div class="team-dot" style="background:${t.color};color:${t.text_color}">${t.short}</div>
      <div class="tname">${esc(t.name)}</div>
      <div class="tby">${t.occupied_by ? "Taken by " + esc(t.occupied_by) : "Available"}</div>`;
    if (!t.occupied_by) d.onclick = () => { pickedTeam = t.id; renderLobby(); };
    g.appendChild(d);
  });
  // mode cards
  const mc = $("modeCards"); mc.innerHTML = "";
  Object.entries(S.modes).forEach(([key, m]) => {
    const d = document.createElement("div");
    d.className = "mode-card";
    d.innerHTML = `<h3>${esc(m.label)}</h3><div class="purse">₹${m.purse_cr} Cr <small style="font-size:13px;color:var(--mut)">purse</small></div>
      <p>${esc(m.blurb)}<br>Squad: ${m.squad_size} players · Overseas ${m.min_overseas}–${m.max_overseas}</p>
      <button class="btn primary" ${S.me ? "" : "disabled"}>Start ${esc(m.label)}</button>`;
    d.querySelector("button").onclick = async () => {
      const r = await api(R("/start"), "POST", { token: store.token, mode: key });
      if (!r.ok) $("startMsg").textContent = r.error || "Could not start.";
    };
    mc.appendChild(d);
  });
  if (S.me) {
    $("whoami").classList.remove("hidden");
    const t = S.teams[S.me.team_id];
    $("whoami").innerHTML = `You are <b>${esc(S.me.name)}</b> bidding for <b style="color:${t.color}">${esc(t.name)}</b>${S.me.is_host ? ' · <span class="host-tag">HOST</span>' : ''} <a href="#" id="leaveLink" style="color:var(--mut);font-size:13px">leave</a>`;
    $("leaveLink").onclick = async (e) => { e.preventDefault(); await api(R("/leave"), "POST", { token: store.token }); store.token = ""; pickedTeam = null; poll(); };
    $("joinBtn").disabled = true;
  } else {
    $("whoami").classList.add("hidden");
    $("joinBtn").disabled = false;
  }
}

function renderStage() {
  const a = S.auction, cur = S.current;
  const host = S.me && S.me.is_host;
  if (a.status === "done") {
    $("setTag").textContent = "Auction complete";
    $("playerCard").innerHTML = `<div class="p-info"><h2>🎉 That's the auction!</h2>
      <p class="p-meta">All players have gone under the hammer. Check the Sold tab for final squads.</p></div>`;
    $("currentBid").innerHTML = "";
    $("bidBtn").disabled = true; $("bidBtn").textContent = "Auction Over";
    $("timerText").textContent = "";
    $("hostControls").classList.toggle("hidden", !host);
    return;
  }
  if (!cur) return;
  const p = cur.player;
  $("setTag").textContent = p.set_name;
  const canPhoto = host ? `<div style="margin-top:8px"><a href="#" id="photoLink" style="font-size:12px;color:var(--mut)">set photo URL</a></div>` : "";
  $("playerCard").innerHTML = `${avatarHTML(p, "p-avatar")}
    <div class="p-info"><h2>${esc(p.name)}</h2>
      <div class="p-meta">${FLAG[p.country] || "🏏"} ${esc(p.country)} · ${ROLE[p.role] || p.role}</div>
      <div class="p-base">Base price: ${fmtLakh(p.base_lakh)}</div>
      ${statsLine(p) ? `<div class="p-stats">${statsLine(p)}</div>` : ""}${canPhoto}</div>`;
  if (host && $("photoLink")) $("photoLink").onclick = async (e) => {
    e.preventDefault();
    const url = prompt("Paste a photo URL for " + p.name + " (blank to clear):", p.img || "");
    if (url !== null) await api(R("/player_image"), "POST", { token: store.token, player_id: p.id, img_url: url });
  };
  if (cur.bid_lakh) {
    const t = cur.team;
    $("currentBid").innerHTML = `<div class="cb-label">Current bid</div>
      <div class="cb-amount">${fmtLakh(cur.bid_lakh)}</div>
      <div class="cb-team" style="background:${teamColor(t.id)};color:${teamText(t.id)}">${esc(t.name)}${cur.bidder_name ? " · " + esc(cur.bidder_name) : ""}</div>`;
  } else {
    $("currentBid").innerHTML = `<div class="cb-label">Awaiting first bid</div>
      <div class="cb-amount" style="font-size:30px">Base ${fmtLakh(p.base_lakh)}</div>`;
  }
  const mine = S.me && cur.team && cur.team.id === S.me.team_id;
  $("bidBtn").disabled = !S.me || !cur || mine || a.status !== "bidding";
  $("bidBtn").textContent = !S.me ? "Join to bid" : mine ? "You hold the bid" : `Bid ${fmtLakh(cur.next_bid_lakh)}`;
  $("hostControls").classList.toggle("hidden", !host || (a.status !== "bidding" && a.status !== "result"));
  updateTimer();
}

function updateTimer() {
  if (!S || !S.auction.mode) return;
  const a = S.auction, cur = S.current;
  if (a.status !== "bidding" || !cur) { $("timerBar").style.width = "0%"; return; }
  const elapsed = Date.now() / 1000 - (S.clientNow || Date.now() / 1000);
  const left = Math.max(0, cur.deadline - S.now - elapsed);
  const pct = Math.min(100, (left / 20) * 100);
  $("timerBar").style.width = pct + "%";
  $("timerText").textContent = left > 0 ? (left < 4 ? "🔨 Hammer coming…" : `${Math.ceil(left)}s left`) : "";
}

function teamColor(id) { return S.teams[id].color; }
function teamText(id) { return S.teams[id].text_color; }

function renderSide() {
  const me = S.me;
  const ts = $("teamsStrip"); ts.innerHTML = "";
  S.teams.forEach(t => {
    if (!t.squad) return;
    const sq = t.squad, cfg = S.auction.mode_cfg;
    const d = document.createElement("div");
    d.className = "tm" + (me && me.team_id === t.id ? " me" : "");
    d.innerHTML = `<div class="hd"><span class="dot" style="background:${t.color}"></span>${t.short}</div>
      <div class="st">${t.occupied_by ? esc(t.occupied_by) : "<i>no bidder</i>"}</div>
      <div class="st"><b>${sq.count}</b>/${cfg.squad_size} players · <b>${sq.overseas}</b> ✈️</div>
      <div class="st">Purse: <b>${fmtLakh(sq.remaining_lakh)}</b></div>`;
    ts.appendChild(d);
  });
  if (me && S.teams[me.team_id].squad) {
    const t = S.teams[me.team_id], sq = t.squad, cfg = S.auction.mode_cfg;
    $("mySquadTitle").textContent = `${t.short} · My Squad (${sq.count}/${cfg.squad_size}, ✈️${sq.overseas})`;
    const total = cfg.purse_cr * 100;
    $("purseFill").style.width = (sq.remaining_lakh / total * 100) + "%";
    $("purseText").textContent = `Purse left ${fmtLakh(sq.remaining_lakh)} of ${fmtLakh(total)} · Spent ${fmtLakh(sq.spent_lakh)}`;
    const ml = $("mySquadList"); ml.innerHTML = sq.players.length ? "" : `<div style="color:var(--mut);font-size:13px">No players yet — win some bids!</div>`;
    [...sq.players].sort((x, y) => y.sold_price_lakh - x.sold_price_lakh).forEach(p => {
      const r = document.createElement("div");
      r.className = "sq-row";
      r.innerHTML = `<span>${FLAG[p.country] || ""} ${esc(p.name)} <small style="color:var(--mut)">${ROLE[p.role] || ""}</small></span><span class="pr">${fmtLakh(p.sold_price_lakh)}</span>`;
      ml.appendChild(r);
    });
  } else {
    $("mySquadTitle").textContent = "My Squad";
    $("mySquadList").innerHTML = `<div style="color:var(--mut);font-size:13px">Join a team to build your squad.</div>`;
  }
}

function playerRow(p, extra = "") {
  const live = S.current && S.current.player.id === p.id && S.auction.status === "bidding";
  const done = p.status !== "upcoming";
  let right;
  if (p.status === "sold") {
    const t = S.teams[p.sold_team_id];
    right = `<span class="sold-tag" style="background:${t.color};color:${t.text_color}">${t.short} · ${fmtLakh(p.sold_price_lakh)}</span>`;
  } else if (p.status === "unsold") {
    right = `<span class="sold-tag" style="background:#2a2f45;color:var(--mut)">UNSOLD</span>`;
  } else right = `<span class="bs">${fmtLakh(p.base_lakh)}</span>`;
  return `<div class="prow${live ? " live" : ""}${done ? " done" : ""}">${avatarHTML(p, "mini-av")}
    <div><div class="nm">${esc(p.name)}</div><div class="rl">${FLAG[p.country] || ""} ${ROLE[p.role] || p.role}${extra}</div>${statsLine(p) ? `<div class="rl stats-compact">${statsLine(p)}</div>` : ""}</div>${right}</div>`;
}

function renderLists() {
  const sets = S.sets;
  // upcoming grouped set-by-set
  const up = $("tab-upcoming"); up.innerHTML = "";
  sets.forEach(s => {
    const h = document.createElement("div");
    h.className = "set-head";
    const n = s.players.filter(p => p.status === "upcoming").length;
    h.textContent = `${s.name} (${n} to go)`;
    up.appendChild(h);
    const g = document.createElement("div"); g.className = "plist";
    s.players.forEach(p => { g.innerHTML += playerRow(p); });
    up.appendChild(g);
  });
  // sold
  const sold = [];
  sets.forEach(s => s.players.forEach(p => { if (p.status === "sold") sold.push(p); }));
  sold.sort((x, y) => y.sold_price_lakh - x.sold_price_lakh);
  $("soldCount").textContent = sold.length ? `(${sold.length})` : "";
  const sp = $("tab-sold"); sp.innerHTML = sold.length ? "" : `<p style="color:var(--mut)">No players sold yet.</p>`;
  if (sold.length) {
    const g = document.createElement("div"); g.className = "plist";
    sold.forEach((p, i) => { g.innerHTML += playerRow(p, ` · #${i + 1}`); });
    sp.appendChild(g);
  }
  // unsold
  const un = [];
  sets.forEach(s => s.players.forEach(p => { if (p.status === "unsold") un.push(p); }));
  $("unsoldCount").textContent = un.length ? `(${un.length})` : "";
  const np = $("tab-unsold"); np.innerHTML = un.length ? "" : `<p style="color:var(--mut)">No unsold players. Yet.</p>`;
  if (un.length) {
    const g = document.createElement("div"); g.className = "plist";
    un.forEach(p => { g.innerHTML += playerRow(p); });
    np.appendChild(g);
  }
}

function renderOverlay() {
  const a = S.auction, ov = $("resultOverlay");
  if (a.status === "result" && a.mode && S.last) {
    const p = S.last.player;
    if (S.last.result === "sold") {
      const t = S.teams[p.sold_team_id];
      $("resultCard").innerHTML = `<div class="confetti">🎉🏆🎉</div><h1>SOLD!</h1>
        <div style="font-size:22px;font-weight:800">${esc(p.name)}</div>
        <div class="rteam" style="color:${t.color==="#111111"||t.color==="#F9CD05"?"var(--gold)":t.color}">${esc(t.name)}</div>
        <div class="rprice">${fmtLakh(p.sold_price_lakh)}</div>
        <p>Congratulations, ${esc(t.name)}! What a buy! 👏</p>`;
    } else {
      $("resultCard").innerHTML = `<div class="confetti">😶</div><h1>UNSOLD</h1>
        <div style="font-size:22px;font-weight:800">${esc(p.name)}</div>
        <p>No bids. ${esc(p.name)} goes back to the pool unsold.</p>`;
    }
    ov.classList.remove("hidden");
  } else ov.classList.add("hidden");
}

/* ---------------- actions ---------------- */
document.querySelectorAll("[data-authtab]").forEach(t => t.onclick = () => {
  document.querySelectorAll("[data-authtab]").forEach(x => x.classList.remove("active"));
  t.classList.add("active");
  const tab = t.dataset.authtab;
  $("pane-login").classList.toggle("hidden", tab !== "login");
  $("pane-register").classList.toggle("hidden", tab !== "register");
});
async function authDone(r, msgEl) {
  if (r.ok) {
    store.auth = r.token;
    $(msgEl).textContent = "";
    lastSeq = 0; lastSpokenSeq = 0;
    poll();
  } else $(msgEl).textContent = r.error || "Something went wrong.";
}
$("loginBtn").onclick = async () => {
  const r = await api("/api/auth/login", "POST",
    { name: $("loginName").value.trim(), password: $("loginPass").value });
  authDone(r, "loginMsg");
};
$("registerBtn").onclick = async () => {
  const r = await api("/api/auth/register", "POST",
    { name: $("regName").value.trim(), password: $("regPass").value });
  authDone(r, "regMsg");
};
[$("loginPass"), $("regPass")].forEach(el => el.addEventListener("keydown", (e) => {
  if (e.key === "Enter") (el.id === "loginPass" ? $("loginBtn") : $("registerBtn")).click();
}));
$("logoutBtn").onclick = async () => {
  try { await api("/api/auth/logout", "POST", { token: store.auth }); } catch (e) {}
  logoutLocal();
};
$("createRoomBtn").onclick = async () => {
  const name = $("createNameInput").value.trim();
  if (!name) { $("createMsg").textContent = "Enter your name first."; return; }
  const r = await api("/api/rooms", "POST", { name, auth: store.auth });
  if (r.ok) {
    store.roomCode = r.code;
    $("nameInput").value = name; // prefill for team join
    $("createMsg").textContent = "";
    lastSeq = 0; lastSpokenSeq = 0;
    poll();
  } else $("createMsg").textContent = r.error || "Could not create room.";
};
$("joinRoomBtn").onclick = async () => {
  const code = $("joinCodeInput").value.trim().toUpperCase();
  const name = $("joinNameInput").value.trim();
  if (!code) { $("joinRoomMsg").textContent = "Enter the room code."; return; }
  if (!name) { $("joinRoomMsg").textContent = "Enter your name."; return; }
  const st = await api(`/api/r/${code}/state`);
  if (st && st.ok === false) { $("joinRoomMsg").textContent = st.error || "Room not found."; return; }
  if (!st || st.seq === undefined) { $("joinRoomMsg").textContent = "Could not reach the room."; return; }
  store.roomCode = st.room.code;
  $("nameInput").value = name;
  $("joinRoomMsg").textContent = "";
  lastSeq = 0; lastSpokenSeq = 0;
  poll();
};
$("copyCodeBtn").onclick = async () => {
  try {
    await navigator.clipboard.writeText(store.roomCode);
    $("copyCodeBtn").textContent = "✅ Copied";
    setTimeout(() => $("copyCodeBtn").textContent = "📋 Copy", 2000);
  } catch (e) {
    prompt("Copy your room code:", store.roomCode);
  }
};
$("leaveRoomLink").onclick = async (e) => {
  e.preventDefault();
  if (store.token) { try { await api(R("/leave"), "POST", { token: store.token }); } catch (err) {} }
  leaveRoomLocal();
};
$("joinBtn").onclick = async () => {
  const name = $("nameInput").value.trim();
  if (!name) { $("joinMsg").textContent = "Enter your name first."; return; }
  if (pickedTeam == null) { $("joinMsg").textContent = "Pick your team above."; return; }
  const r = await api(R("/join"), "POST", { name, team_id: pickedTeam, auth: store.auth });
  if (r.ok) { store.token = r.token; $("joinMsg").textContent = ""; poll(); }
  else $("joinMsg").textContent = r.error || "Could not join.";
};
$("bidBtn").onclick = async () => {
  const r = await api(R("/bid"), "POST", { token: store.token });
  if (!r.ok) { $("bidMsg").textContent = r.error || "Bid failed."; setTimeout(() => $("bidMsg").textContent = "", 3500); }
};
document.addEventListener("keydown", (e) => {
  if ((e.key === "b" || e.key === "B") && !$("view-auction").classList.contains("hidden")
      && document.activeElement.tagName !== "INPUT") $("bidBtn").click();
});
$("hammerBtn").onclick = () => api(R("/hammer"), "POST", { token: store.token }).then(poll);
$("unsoldBtn").onclick = () => api(R("/mark_unsold"), "POST", { token: store.token }).then(poll);
$("nextBtn").onclick = () => api(R("/next"), "POST", { token: store.token }).then(poll);
$("resetBtn").onclick = async () => {
  if (confirm("Reset the whole auction? (Teams stay joined.)"))
    await api(R("/reset"), "POST", { token: store.token }).then(poll);
};
$("voiceToggle").onclick = () => {
  voiceOn = !voiceOn;
  $("voiceToggle").textContent = voiceOn ? "🔊" : "🔇";
  $("voiceToggle").classList.toggle("on", voiceOn);
  if (!voiceOn && "speechSynthesis" in window) speechSynthesis.cancel();
};
document.querySelectorAll(".lists-card .tab").forEach(t => t.onclick = () => {
  document.querySelectorAll(".lists-card .tab").forEach(x => x.classList.remove("active"));
  t.classList.add("active"); activeTab = t.dataset.tab;
  ["upcoming", "sold", "unsold"].forEach(k => $("tab-" + k).classList.toggle("hidden", k !== activeTab));
});

showView("auth");
poll();
