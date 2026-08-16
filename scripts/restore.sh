#!/usr/bin/env bash
set -e

if [ -z "$1" ]; then
  echo "Usage: $0 /opt/bristlecone/backups/postgres_bristlecone_YYYYMMDD_HHMMSS.sql.gz"
  echo ""
  echo "Available snapshots:"
  ls -lh /opt/bristlecone/backups/*.sql.gz 2>/dev/null || echo "No backups found."
  exit 1
fi

BACKUP_FILE="$1"

if [ ! -f "$BACKUP_FILE" ]; then
  echo "Error: Backup file '$BACKUP_FILE' does not exist."
  exit 1
fi

echo "=================================================="
echo "   BRISTLECONE LOGIC DATABASE RESTORE UTILITY     "
echo "=================================================="
echo "Target snapshot: $BACKUP_FILE"
read -p "WARNING: This will overwrite the live database. Continue? (y/N): " CONFIRM
if [[ "$CONFIRM" != "y" && "$CONFIRM" != "Y" ]]; then
  echo "Restore aborted."
  exit 0
fi

echo "[1/3] Terminating active connections & recreating database..."
docker compose exec -T db psql -U postgres -c "
SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = 'bristlecone_db' AND pid <> pg_backend_pid();
DROP DATABASE IF EXISTS bristlecone_db;
CREATE DATABASE bristlecone_db;
"

echo "[2/3] Restoring database snapshot from archive..."
gunzip -c "$BACKUP_FILE" | docker compose exec -T db psql -U postgres -d bristlecone_db

echo "[3/3] Restarting dependent services & verifying..."
docker compose restart api worker
./scripts/wait_for_api.sh

echo ""
echo "Database successfully restored and services re-synchronized."
