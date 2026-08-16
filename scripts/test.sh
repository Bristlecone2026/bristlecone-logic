#!/usr/bin/env bash
set -e

# Ensure services are healthy
./scripts/wait_for_api.sh

echo ""
echo "=== Running Bristlecone Integration Suite ==="
docker compose exec -T \
  -e PYTHONPATH=/app \
  -e GATEWAY_URL=http://nginx/api/v1 \
  api python3 tests/test_suite.py
