#!/bin/bash
# Removes everything install.sh added. Safe to run on the Proxmox host.
set -euo pipefail
if [ "$(id -u)" -ne 0 ]; then echo "run as root" >&2; exit 1; fi
systemctl disable --now hq-kiosk.service 2>/dev/null || true
rm -f /etc/systemd/system/hq-kiosk.service /usr/local/bin/hq-chromium
rm -rf /etc/hq
systemctl daemon-reload
systemctl enable getty@tty1.service 2>/dev/null || true
systemctl set-default multi-user.target
userdel -r kiosk 2>/dev/null || true
apt-get remove -y cage chromium mesa-vulkan-drivers fonts-noto-core || true
apt-get autoremove -y
# firmware-amd-graphics is left installed: harmless and useful for the iGPU.
echo "Kiosk removed."
