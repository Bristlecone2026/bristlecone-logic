# Terminal Sandbox Quick Start

Test Bristlecone Logic runtime defenses and ledger state in 5 seconds from any terminal using `curl`. 

All sandbox endpoints are zero-auth and rate-limited to **5 requests per minute per IP**.

### 1. Test SSRF CIDR Blocking (AWS Metadata IP Probe)
Verifies that the pre-socket DNS pre-flight filter blocks internal cloud metadata endpoints (`169.254.169.254`).

```bash
curl -s -X POST https://api.bristleconelogic.com/v1/sandbox/audit-dns \
  -H "Content-Type: application/json" \
  -d '{"domain": "169.254.169.254"}' | jq .
```

### 2. Test Deterministic LLM JSON Repair
Demonstrates AST-isolated recovery of truncated or malformed JSON payloads produced by LLMs.

```bash
curl -s -X POST https://api.bristleconelogic.com/v1/sandbox/repair-json \
  -H "Content-Type: application/json" \
  -d '{"raw_json": "{\"agent\": \"claude\", \"status\": \"active\", \"items\": [1, 2, 3"}' | jq .
```

### 3. Test AST-Isolated Math Evaluation
Performs deterministic calculations inside a sandboxed AST environment.

```bash
curl -s -X POST https://api.bristleconelogic.com/v1/sandbox/eval-expression \
  -H "Content-Type: application/json" \
  -d '{"expression": "((1500 * 12) / 4) + 250.75"}' | jq .
```

### 4. Test Live XRPL Mainnet Ledger State
Queries the live XRPL Mainnet for the latest validated ledger index and close timestamp.

```bash
curl -s https://api.bristleconelogic.com/v1/sandbox/xrpl-ledger | jq .
```
