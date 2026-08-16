#!/usr/bin/env bash
set -e

BACKUP_DIR="/opt/bristlecone/backups"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
DB_BACKUP="${BACKUP_DIR}/postgres_bristlecone_${TIMESTAMP}.sql.gz"
REDIS_BACKUP="${BACKUP_DIR}/redis_dump_${TIMESTAMP}.rdb"

mkdir -p "${BACKUP_DIR}"

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting Bristlecone Logic snapshot..."

# 1. PostgreSQL Database Dump (Compressed)
docker compose -f /opt/bristlecone/bristlecone-logic/docker-compose.yml exec -T db \
  pg_dump -U postgres bristlecone_db | gzip > "${DB_BACKUP}"

echo "  -> PostgreSQL snapshot created: ${DB_BACKUP} ($(du -h "${DB_BACKUP}" | cut -f1))"

# 2. Redis RDB Snapshot
docker compose -f /opt/bristlecone/bristlecone-logic/docker-compose.yml exec -T redis \
  redis-cli bgsave > /dev/null 2>&1 || true

# Wait for background save to finish
sleep 2

REDIS_CID=$(docker compose -f /opt/bristlecone/bristlecone-logic/docker-compose.yml ps -q redis)
if [ -n "$REDIS_CID" ]; then
  docker cp "${REDIS_CID}:/data/dump.rdb" "${REDIS_BACKUP}" 2>/dev/null || true
  if [ -f "${REDIS_BACKUP}" ]; then
    echo "  -> Redis snapshot created:      ${REDIS_BACKUP} ($(du -h "${REDIS_BACKUP}" | cut -f1))"
  fi
fi

# 3. Retention Policy: Prune snapshots older than 7 days
find "${BACKUP_DIR}" -type f \( -name "*.sql.gz" -o -name "*.rdb" \) -mtime +7 -exec rm {} +
echo "  -> Retention policy verified (7-day rolling window)."

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Backup complete."
