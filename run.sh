#!/bin/bash

set -e

echo "=================================================="
echo "   Bristlecone Logic Core - Production Boot       "
echo "=================================================="

# 1. Environment & Directory Sanity Check
if [ ! -d "app" ]; then
    echo "[ERROR] 'app' directory not found. Please run this script from the project root."
    exit 1
fi

# 2. Check for .env file or generate default secret
if [ ! -f ".env" ]; then
    echo "[WARN] No .env file detected. Generating production .env with secure HMAC secret..."
    SECRET=$(python3 -c "import secrets; print(secrets.token_hex(32))")
    echo "HMAC_SECRET_KEY=$SECRET" > .env
    echo "[OK] Created .env file."
fi

# 3. Pre-flight Test Execution
echo ""
echo "[1/2] Executing pre-flight security and integrity check..."
if python3 -m pytest tests/test_pipeline.py -q; then
    echo "[OK] Pre-flight verification passed (7/7 tests green)."
else
    echo "[CRITICAL] Pre-flight tests failed! Aborting startup to protect system state."
    exit 1
fi

# 4. Launch Gateway Service
echo ""
echo "[2/2] Booting Layer 5 Gateway API on http://127.0.0.1:8000 ..."
echo "=================================================="
python3 -m uvicorn app.layer5_api.main:app --host 127.0.0.1 --port 8000
