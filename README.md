# HQ

A Skylight-style family hub, self-hosted. One mini PC in the hall runs Proxmox,
Home Assistant and this app, and drives two Corsair Xeneon Edge touchscreens.

Design docs live in the Claude project (architecture v2, development plan).

## Layout

- `app/` — the HQ web app (FastAPI backend + static front-end). Talks to Home
  Assistant over its WebSocket API; browsers talk only to this app.
- `docker-compose.yml` — runs the app on the Docker VM. Copy `.env.example`
  to `.env` and fill in the Home Assistant URL and a long-lived token.
- `kiosk/` — turns any Debian box into a full-screen touch display for HQ.
  `install.sh <url>` / `uninstall.sh`.
- `scripts/` — server housekeeping (backup etc.).

## Run

    cp .env.example .env   # then edit
    docker compose up -d --build
    curl http://localhost:8080/api/health

## Rules

Secrets never go in the repo. One feature at a time. Test on the real screens.
