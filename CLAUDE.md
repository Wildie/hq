# HQ — briefing for Claude Code

You are working on HQ, Rob's self-hosted family hub. Read this before doing anything.

## Who you're working with

Rob is new to Linux and servers but competent at DIY and electrics. He decides design,
feature and implementation choices; you do the hands-on work. Give him one step at a
time, exact commands, and say what he should see. Be concise. Director mode for ideas:
clear verdict, honest critique, best executable version, impact score out of 10.

## What exists (as of 6 Nov 2026)

One Bosgame P3 Lite mini PC (Ryzen 7 6800H, 32GB, 1TB) runs everything:

| Thing | Where | Address |
|---|---|---|
| Proxmox VE 9 (hypervisor) | the physical box, hostname `hq-server` | `https://192.168.18.39:8006`, SSH `root@192.168.18.39` |
| Home Assistant OS | Proxmox VM 100 | `http://192.168.18.47` (port 80 — HA's default; leave it) |
| Docker VM (Debian 13) — **you run here** | Proxmox VM 101, user `rob` | `192.168.18.50` |
| HQ app (this repo) | Docker container `hq` on the Docker VM | `http://192.168.18.50:8080` |
| Kiosk (cage + Chromium) | on the Proxmox host, service `hq-kiosk` | shows the HQ app on a Corsair Xeneon Edge on the USB4 port |
| Tailscale | Proxmox host only | `100.107.243.14` |
| Backups | `/root/hq-backup.sh` on the host, cron 03:00, rclone → Google Drive `hq-backups/` | alerts via ntfy to Rob's phone |

Network: `192.168.18.0/24`, Nokia Beacon router at `.1`. All three IPs above are reserved.

HA integrations: Hue, WiZ, Govee (LAN), tado (HomeKit, local), Elgato, Ring (cloud), Met.no.

## Repo layout

- `app/` — FastAPI backend (`main.py`) + static front-end. Backend holds the HA token and
  bridges browsers to HA's WebSocket API. Browsers only ever talk to this app.
- `docker-compose.yml`, `.env` (secrets, never committed; see `.env.example`).
- `kiosk/` — `install.sh <url>` / `uninstall.sh` / `hq-chromium`. Designed to run on any
  Debian box so the screens can move to a separate client later.
- `scripts/` — reference copies of host scripts.

Deploy a change: `git pull && sudo docker compose up -d --build`, then
`curl -s localhost:8080/api/health` should show `"ha_connected":true`.

## Rules (from the project's development plan)

1. One feature at a time; each works on its own before the next starts.
2. Skylight parity first (calendar, chores, meals, lists, photo frame, home control)
   before any AI or smart extras. The hub must be useful with the AI off.
3. Local first. Kids' data (Screen Time, location, photos) never leaves the house except
   in a backup. Anything that sends data out is named in the architecture doc.
4. No subscriptions without a reason written down.
5. Secrets live in `.env` / `/root/.hq-secrets` / rclone.conf — never in code, commits or chat.
6. Snapshot before anything risky: `qm snapshot <vmid> <name>` on the host.
7. Commit after each working change. Rollback = `git revert` + Proxmox snapshot.
8. Separable: nothing may assume the screens and services are on the same box.
   HQ and HA are always addressed by IP/hostname, never `localhost`.
9. "Feels instant" is a number: the latency panel in the app measures tap → HA confirmed.
   Keep it well under 300 ms.
10. Test on the real Edge screen before calling a feature done.

## Things not to do

- Don't change HA's port or the reserved IPs.
- Don't install desktop/GUI packages on the Proxmox host beyond what `kiosk/install.sh` adds.
- Don't run `apt full-upgrade` on the Proxmox host without a snapshot and Rob's say-so.
- Don't touch `/etc/pve` by hand.

## Where the bigger picture lives

Architecture and plan docs are in Rob's Claude project ("HQ"): `HQ-architecture-v2.md`
and `HQ-development-plan.md`. Build order: 3 skeleton+touch test (done), 4 build-out,
5 hall install, 6 extras. If you make a decision that changes any of that, tell Rob so the
docs get updated.
