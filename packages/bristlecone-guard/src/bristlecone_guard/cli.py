#!/usr/bin/env python3
import json
import os
import sys
import urllib.request
import urllib.error

DEFAULT_ENDPOINT = os.getenv("BRISTLECONE_ENDPOINT", "https://bristleconelogic.com/mcp")
API_KEY = os.getenv("BRISTLECONE_API_KEY")
TENANT_ID = os.getenv("BRISTLECONE_TENANT_ID")

def main():
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "bristlecone-guard/0.1.0"
    }
    if API_KEY:
        headers["Authorization"] = f"Bearer {API_KEY}"
    if TENANT_ID:
        headers["X-Tenant-ID"] = TENANT_ID

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue

        req_id = payload.get("id")
        req_bytes = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(DEFAULT_ENDPOINT, data=req_bytes, headers=headers, method="POST")

        try:
            with urllib.request.urlopen(req, timeout=30.0) as resp:
                body = resp.read().decode("utf-8")
                sys.stdout.write(body + "\n")
                sys.stdout.flush()
        except urllib.error.HTTPError as err:
            err_body = err.read().decode("utf-8", errors="replace")
            err_resp = {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32000, "message": f"Upstream HTTP {err.code}: {err_body}"}
            }
            sys.stdout.write(json.dumps(err_resp) + "\n")
            sys.stdout.flush()
        except Exception as exc:
            err_resp = {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32603, "message": f"Bridge error: {str(exc)}"}
            }
            sys.stdout.write(json.dumps(err_resp) + "\n")
            sys.stdout.flush()

if __name__ == "__main__":
    main()
