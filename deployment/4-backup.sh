#!/bin/bash
# ============================================================================
# Database Backup Script
# Usage: bash 4-backup.sh
# Add to crontab for daily backups: crontab -e
# 0 3 * * * /home/deploy/maxpayads/deployment/4-backup.sh >> /home/deploy/backups/backup.log 2>&1
# ============================================================================
set -e

BACKUP_DIR="/home/deploy/backups"
DATE=$(date +%Y%m%d_%H%M%S)
KEEP_DAYS=7

mkdir -p "$BACKUP_DIR"

echo "[$(date)] Starting backup..."

# ── MongoDB backup ───────────────────────────────────────────────────────────
docker exec ppc_mongodb mongodump \
  --db ppc_network \
  --archive="/backup/ppc_network_${DATE}.gz" \
  --gzip

# Copy from container volume to host
docker cp ppc_mongodb:"/backup/ppc_network_${DATE}.gz" "$BACKUP_DIR/"

echo "[$(date)] MongoDB backup: $BACKUP_DIR/ppc_network_${DATE}.gz"

# ── Cleanup old backups ──────────────────────────────────────────────────────
find "$BACKUP_DIR" -name "ppc_network_*.gz" -mtime +$KEEP_DAYS -delete
echo "[$(date)] Cleaned backups older than $KEEP_DAYS days"

echo "[$(date)] Backup complete!"
