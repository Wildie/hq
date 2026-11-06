#!/bin/bash
# Reference copy of /root/hq-backup.sh on the Proxmox host (installed 5 Nov 2026).
# Nightly: tar Proxmox config -> /var/lib/vz/dump/config, rclone sync dump dir -> Google Drive,
# ntfy on failure, weekly OK. Secrets in /root/.hq-secrets (NTFY_TOPIC) and rclone.conf.
. /root/.hq-secrets
STAMP=$(date +%F)
LOG=/var/log/hq-backup.log
CFG=/var/lib/vz/dump/config
mkdir -p "$CFG"
echo "=== $STAMP $(date +%T) start" >>"$LOG"
tar czf "$CFG/hq-config-$STAMP.tgz" /etc/pve /etc/network/interfaces /etc/hosts /etc/hostname /root/hq-backup.sh /root/.config/rclone/rclone.conf >>"$LOG" 2>&1 \
 && ls -t "$CFG"/hq-config-*.tgz | tail -n +15 | xargs -r rm -- \
 && rclone sync /var/lib/vz/dump gdrive:hq-backups/dump --fast-list >>"$LOG" 2>&1
RC=$?
SIZE=$(rclone size gdrive:hq-backups 2>/dev/null | grep 'Total size' | sed 's/Total size: //')
if [ $RC -ne 0 ]; then
  curl -s -H "Title: HQ backup FAILED" -H "Priority: high" -d "Exit $RC. See /var/log/hq-backup.log" ntfy.sh/$NTFY_TOPIC >/dev/null
elif [ "$(date +%u)" = 7 ] || [ -n "$FORCE_OK" ]; then
  curl -s -H "Title: HQ backup OK" -d "Drive backup size: $SIZE" ntfy.sh/$NTFY_TOPIC >/dev/null
fi
echo "=== $STAMP $(date +%T) end rc=$RC size=$SIZE" >>"$LOG"
exit $RC
