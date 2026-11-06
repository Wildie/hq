#!/bin/bash
# HQ kiosk installer for a Debian-based box (Proxmox host or a separate client).
#
#   sudo ./install.sh http://192.168.18.50:8080
#
# Installs a minimal Wayland compositor (cage) + Chromium, creates a locked-down
# 'kiosk' user, and a systemd service that boots straight into the HQ page on
# the first display. Everything it adds is listed in PACKAGES so uninstall.sh
# can remove it cleanly.
set -euo pipefail

URL="${1:?usage: install.sh <HQ URL>}"
KIOSK_UID=1500
PACKAGES="cage chromium mesa-vulkan-drivers libgl1-mesa-dri fonts-noto-core"

if [ "$(id -u)" -ne 0 ]; then echo "run as root" >&2; exit 1; fi
. /etc/os-release

# GPU firmware. Proxmox hosts already have it via pve-firmware, which conflicts
# with Debian's firmware-amd-graphics, so only plain Debian boxes get that.
if ! dpkg -s pve-firmware >/dev/null 2>&1; then
  if ! grep -rqs non-free-firmware /etc/apt/sources.list /etc/apt/sources.list.d/; then
    cat > /etc/apt/sources.list.d/hq-firmware.sources <<EOF
Types: deb
URIs: http://deb.debian.org/debian
Suites: ${VERSION_CODENAME}
Components: non-free-firmware
Signed-By: /usr/share/keyrings/debian-archive-keyring.gpg
EOF
  fi
  PACKAGES="$PACKAGES firmware-amd-graphics"
fi

apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends $PACKAGES

# Kiosk user: no password, no shell login, just display/input access.
if ! id kiosk >/dev/null 2>&1; then
  useradd --uid "$KIOSK_UID" --create-home --shell /usr/sbin/nologin --groups video,input,render kiosk
fi

install -m 0755 "$(dirname "$0")/hq-chromium" /usr/local/bin/hq-chromium
mkdir -p /etc/hq
echo "HQ_URL=$URL" > /etc/hq/kiosk.env

cat > /etc/systemd/system/hq-kiosk.service <<EOF
[Unit]
Description=HQ kiosk display
After=systemd-user-sessions.service network-online.target
Wants=network-online.target
Conflicts=getty@tty1.service

[Service]
User=kiosk
PAMName=login
TTYPath=/dev/tty1
StandardInput=tty
StandardOutput=journal
StandardError=journal
EnvironmentFile=/etc/hq/kiosk.env
Environment=XDG_RUNTIME_DIR=/run/user/$KIOSK_UID
Environment=XDG_SESSION_TYPE=wayland
ExecStart=/usr/bin/cage -s -- /usr/local/bin/hq-chromium
Restart=always
RestartSec=3

[Install]
WantedBy=graphical.target
EOF

systemctl daemon-reload
systemctl disable getty@tty1.service >/dev/null 2>&1 || true
systemctl enable hq-kiosk.service
systemctl set-default graphical.target
echo
echo "Installed. Start now with:  systemctl start hq-kiosk"
echo "Logs:                       journalctl -u hq-kiosk -f"
echo "Change the URL in /etc/hq/kiosk.env then: systemctl restart hq-kiosk"
