<div align="center">

# 🏏 IPL Auction Arena
### A full-stack, real-time cricket auction game — create a room, pick a team, bid live

**Create a room and share the 6-letter room code — friends join from their own browsers, each picks one of the 10 IPL franchises (one bidder per team), and bid live for players to build their own squad. Every room runs its own separate auction.**

[![Live Site](https://img.shields.io/badge/Live_Site-ipl--auction--arena--npaj.onrender.com-0d9488?style=for-the-badge)](https://ipl-auction-arena-npaj.onrender.com)
[![Stack](https://img.shields.io/badge/Stack-Flask_%7C_SQLite_%7C_JS-8b5cf6?style=for-the-badge)](https://github.com/1nc24cs146-cmyk/ipl-auction-arena)
[![Players](https://img.shields.io/badge/Players-310-10b981?style=for-the-badge)](#-modes--player-pool)

[🚀 Run it](#-run-it) •
[🌍 Deploy it](#-deploy-it-so-friends-can-join-from-anywhere) •
[🎮 How it plays](#-how-it-plays) •
[📧 Email setup](#-email-setup-required-for-otp-login)

</div>

---

## 📊 At a glance

| | |
|---|---|
| **Live site** | https://ipl-auction-arena-npaj.onrender.com |
| **Stack** | Python + Flask + SQLite backend, vanilla JS frontend, Web Speech API for the auctioneer voice. No build step |
| **Login** | Gmail OTP by email (6-digit code, 10-minute expiry) via the Brevo HTTPS API |
| **Rooms** | 6-letter codes, public rooms with presence and QR join, one team per account per room |
| **Player pool** | 310 players from the IPL 2025 and 2026 squads |
| **Bidding** | Fast bidding — single-click guard, optimistic display, 1-second poll, official IPL bid increments |
| **Voice** | Female auctioneer voice announcing bids and winners, with captions |

## 🚀 Run it

```bash
cd ~/workspace/cricket-auction
chmod +x run.sh
./run.sh
```

Open **http://localhost:5000** in your browser.
Friends on the same Wi-Fi join via `http://<your-computer-ip>:5000`.

Player data, bids, squads and auction state are stored in `auction.db`
(SQLite) — everything persists in the backend.

## 🎮 Modes & player pool

| Mode | Purse | Squad | Overseas | Player pool |
|------|-------|-------|----------|-------------|
| **IPL 2025-26 Auction** | ₹120 Cr | 25 players | 8 overseas | All 310 players — Marquee A, B, C, then capped sets by role, then uncapped sets by role |
| **Mini Auction** | ₹60 Cr | 8 players | min 2, max 4 | Marquee A, B, C + capped sets (no uncapped players) |
| **Quick Auction** | ₹30 Cr | 6 players | max 3 | Short format — Marquee + early capped sets |

Base prices are game-design suggestions (₹2 Cr marquee stars, ₹75L/₹1 Cr/₹1.5 Cr capped, ₹30L uncapped), not a verified official table.

## 🎮 How it plays

1. **Log in or register with your Gmail** — enter your email, get a 6-digit code by email, enter it. Codes expire in 10 minutes.
2. **Create a room** (you get a 6-letter code — you become the room owner) or **join** with a code or QR. Share the code with friends. Public rooms show live presence.
3. Enter your name, pick your favourite IPL team (taken teams are locked — one bidder per team). Everyone waits in the **lobby**, which shows every team with its bidder's name.
4. **Only the room owner** can start the match, and only once **at least 5 bidders** have joined the lobby.
5. The owner picks an auction mode and becomes the **host**.
6. Players come up **set by set**, exactly like the real IPL auction: Marquee A → Marquee B → Marquee C → Capped Batters → All-Rounders → Wicket-Keepers → Fast Bowlers → Spinners → Uncapped sets by role.
7. Hit **BID** (or press `B`) — bids rise by official IPL increments (₹5L under ₹1 Cr, ₹10L to ₹2 Cr, ₹20L to ₹5 Cr, ₹25L above).
8. The 🎙️ **female auctioneer voice** announces every bid ("*Mumbai Indians bid 2 crore 20 lakh for Rishabh Pant*") and congratulates the winning team on every sale.
9. The hammer falls automatically when the timer runs out, or the host can hammer / mark unsold / skip ahead. The result banner shows for 1 second.
10. Track everything in the **Upcoming / Sold / Unsold** tabs and watch every team's purse and squad build in real time.

Leaving from the top bar exits the room while staying logged in; full logout is on the rooms page.

### Squad rules (enforced by the backend)

- Can't exceed your squad size or overseas cap.
- Must still be able to meet the overseas minimum with remaining slots.
- A bid can't leave you unable to fill the rest of your squad at base price.

### Extras

- Host can attach a real photo URL to any player card (host-only "set photo URL" link on the live player card). Cards without a photo show a stylish initials avatar.
- Voice toggle in the top bar; every announcement also appears as a caption.

## 🌍 Deploy it (so friends can join from anywhere)

The app is ready to deploy as a Python web service (tested with gunicorn). Easiest free route — **Render**:

1. Put this folder in a GitHub repo (`.gitignore` already excludes `venv/`, `__pycache__/` and `auction.db`).
2. Go to [render.com](https://render.com) → **New → Web Service** → connect your repo. (Or use the `render.yaml` in this folder as a Blueprint.)
3. Settings: **Runtime** Python, **Build command** `pip install -r requirements.txt`, **Start command** `gunicorn app:app --bind 0.0.0.0:$PORT --workers 1 --threads 8 --timeout 120`.
4. Deploy — you'll get a public URL like `https://ipl-auction-arena-npaj.onrender.com`. Share it with friends.

> ⚠️ One caveat: on free hosting the SQLite database resets when the service restarts or sleeps, so rooms only last for your game session. For a game night that's all you need — everyone just creates a fresh room and plays. (Render's free tier also sleeps after ~15 minutes idle, so the first visit takes ~60 seconds to wake up.)

Railway and Fly.io work too — same build/start commands.

### 📧 Email setup (required for OTP login)

Login codes are emailed through **Brevo's HTTPS API**. (Gmail SMTP does not work from Render — Render blocks outbound SMTP ports 25/465/587, so the Gmail route below is kept only as a local-development fallback.)

Add these environment variables (on Render: **Environment** tab):

| Variable        | Value                                            |
|-----------------|--------------------------------------------------|
| `MAIL_USER`     | the Gmail address codes appear to come from      |
| `BREVO_API_KEY` | a Brevo API key (starts with `xkeysib-`)         |

Brevo setup (free tier, no domain needed):

1. Sign up at brevo.com with the same Gmail.
2. Verify the sender: **Senders, Domains & Dedicated IPs → Senders → Add a sender** — name `IPL Auction Arena`, email = your Gmail → click the confirmation link Brevo emails to that inbox.
3. Create a key: **Settings → SMTP & API → API Keys → Generate a new API key**, and paste it into `BREVO_API_KEY` on Render.

Gmail SMTP fallback (local development only): if `BREVO_API_KEY` is unset, codes are sent via Gmail SMTP using `MAIL_APP_PASSWORD` — a Gmail **App Password** (16 letters; Google Account → Security → turn on **2-Step Verification** → **App passwords**). Never use your normal Gmail password. With no email route configured, requesting a code fails with a clear message (and never leaks the code).

You can check the live mail setup at any time: `GET /api/auth/mail_status` returns `{"mail_ok": true, "status": "ok"}` when codes can be sent.

## 🛠️ Tech

Python + Flask + SQLite backend, vanilla JS frontend, Web Speech API for the auctioneer voice. No build step, no accounts — just open and play.

---

*IPL Auction Arena — Developed by NitinKumar Hiremath.*
