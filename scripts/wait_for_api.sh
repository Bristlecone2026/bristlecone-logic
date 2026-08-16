#!/usr/bin/env bash
set -e

URL="${1:-http://127.0.0.1/api/v1/health}"
MAX_RETRIES=60
RETRY_INTERVAL=1

echo -n "Waiting for Bristlecone Gateway to become healthy"
for ((i=1; i<=MAX_RETRIES; i++)); do
    # Probe endpoint for status code
    STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$URL" 2>/dev/null || true)
    
    if [ "$STATUS" = "200" ]; then
        echo " -> Ready! (HTTP 200 OK)"
        exit 0
    fi
    
    echo -n "."
    sleep "$RETRY_INTERVAL"
done

echo ""
echo "ERROR: Gateway failed healthcheck after ${MAX_RETRIES}s (Last HTTP code: ${STATUS:-unreachable})"
exit 1
