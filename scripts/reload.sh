#!/usr/bin/env bash
set -e

echo "=== Restarting Bristlecone API & Worker Stack ==="
docker compose restart api worker

echo ""
./scripts/wait_for_api.sh

echo ""
echo "=== Verification Payload ==="
curl -s http://127.0.0.1/api/v1/health | jq .
