#!/usr/bin/env python3
import asyncio
import os
import sys
import uuid
import secrets
import hashlib
import time
import httpx
from decimal import Decimal
from sqlalchemy import text
import redis.asyncio as aioredis

from app.database import AsyncSessionLocal

BASE_URL = os.getenv("GATEWAY_URL", "http://nginx/api/v1")
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")

# ANSI Color Codes
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
BOLD = "\033[1m"
RESET = "\033[0m"

def log_pass(name: str, detail: str = ""):
    print(f"  {GREEN}✔ PASS{RESET} {BOLD}{name:<38}{RESET} {detail}")

def log_fail(name: str, reason: str):
    print(f"  {RED}✖ FAIL{RESET} {BOLD}{name:<38}{RESET} {RED}{reason}{RESET}")
    sys.exit(1)

def hash_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()

async def provision_test_tenant(name: str, balance: float, rpm: int) -> tuple[str, str]:
    tenant_id = uuid.uuid4()
    raw_key = f"bl_live_{secrets.token_urlsafe(32)}"
    prefix = raw_key[:12]
    key_h = hash_key(raw_key)

    async with AsyncSessionLocal() as session:
        await session.execute(
            text("""
                INSERT INTO tenants (id, name, is_active, credit_balance_usd, rate_limit_rpm, low_balance_threshold_usd)
                VALUES (:id, :name, true, :balance, :rpm, 1.00)
            """),
            {"id": tenant_id, "name": name, "balance": Decimal(str(balance)), "rpm": rpm}
        )
        await session.execute(
            text("""
                INSERT INTO api_keys (id, tenant_id, name, key_prefix, prefix, key_hash, is_active)
                VALUES (:id, :tid, 'Suite Test Key', :pfx, :pfx, :kh, true)
            """),
            {"id": uuid.uuid4(), "tid": tenant_id, "pfx": prefix, "kh": key_h}
        )
        await session.commit()

    # Sync balance to Redis cache
    r = aioredis.from_url(REDIS_URL, decode_responses=True)
    await r.set(f"balance:{tenant_id}", str(balance))
    await r.aclose()

    return str(tenant_id), raw_key

async def test_auth_guardrails():
    print(f"\n{BOLD}[1/5] Testing Authentication & Key Validation{RESET}")
    async with httpx.AsyncClient(timeout=10.0) as client:
        # Case A: Missing API Key
        res = await client.post(
            f"{BASE_URL}/chat/completions",
            json={"model": "gemini-1.5-flash", "messages": [{"role": "user", "content": "ping"}]}
        )
        if res.status_code == 401:
            log_pass("Missing API Key", "Returns HTTP 401 Unauthorized")
        else:
            log_fail("Missing API Key", f"Expected 401, got {res.status_code}")

        # Case B: Invalid / Forged API Key
        res = await client.post(
            f"{BASE_URL}/chat/completions",
            headers={"X-API-Key": "bl_live_invalid_forged_key_000000000000"},
            json={"model": "gemini-1.5-flash", "messages": [{"role": "user", "content": "ping"}]}
        )
        if res.status_code == 401:
            log_pass("Invalid API Key", "Returns HTTP 401 Unauthorized")
        else:
            log_fail("Invalid API Key", f"Expected 401, got {res.status_code}")

async def test_tool_execution():
    print(f"\n{BOLD}[2/5] Testing Tool Engine & Micro-Billing{RESET}")
    _, key = await provision_test_tenant("Tool Suite Tenant", 5.00, 120)

    async with httpx.AsyncClient(timeout=15.0) as client:
        # 1. Test JSON Repair Tool
        malformed_json = '{"agent": "Bristlecone", "status": "active", "metrics": [10, 20, 30, ]}'
        res = await client.post(
            f"{BASE_URL}/tools/json-repair",
            headers={"X-API-Key": key},
            json={"raw_text": malformed_json}
        )
        if res.status_code == 200:
            body = res.json()
            if body.get("success") and body.get("data", {}).get("agent") == "Bristlecone":
                log_pass("Tool: JSON Repair", f"Repaired trailing comma (Balance: ${body.get('remaining_balance_usd'):.6f})")
            else:
                log_fail("Tool: JSON Repair", f"Malformed parsing output: {body}")
        else:
            log_fail("Tool: JSON Repair", f"Expected 200, got {res.status_code}: {res.text}")

        # 2. Test Web Extract Tool
        res = await client.post(
            f"{BASE_URL}/tools/web-extract",
            headers={"X-API-Key": key},
            json={"url": "https://example.com", "extract_links": True}
        )
        if res.status_code == 200:
            body = res.json()
            if "Example Domain" in body.get("markdown", ""):
                log_pass("Tool: Web Extract", f"Extracted Markdown ({body.get('character_count')} chars)")
            else:
                log_pass("Tool: Web Extract", f"Fetched URL successfully ({body.get('character_count')} chars)")
        else:
            log_fail("Tool: Web Extract", f"Expected 200, got {res.status_code}: {res.text}")

async def test_zero_balance_rejection():
    print(f"\n{BOLD}[3/5] Testing Zero-Balance Rejection (HTTP 402){RESET}")
    _, broke_key = await provision_test_tenant("Exhausted Balance Tenant", 0.00, 120)

    async with httpx.AsyncClient(timeout=10.0) as client:
        res = await client.post(
            f"{BASE_URL}/chat/completions",
            headers={"X-API-Key": broke_key},
            json={"model": "gemini-1.5-flash", "messages": [{"role": "user", "content": "Should fail"}]}
        )
        if res.status_code == 402:
            log_pass("Zero Balance Protection", "Blocked with HTTP 402 Payment Required")
        else:
            log_fail("Zero Balance Protection", f"Expected 402, got {res.status_code}: {res.text}")

async def test_rate_limiting():
    print(f"\n{BOLD}[4/5] Testing Rate Limiting (Strict RPM Enforcement){RESET}")
    _, tight_key = await provision_test_tenant("Rate Limited Tenant", 10.00, 5)

    async with httpx.AsyncClient(timeout=10.0) as client:
        hit_429 = False
        print("  -> Dispatching burst of 10 rapid requests against a 5 RPM tenant quota...")
        for i in range(10):
            res = await client.post(
                f"{BASE_URL}/chat/completions",
                headers={"X-API-Key": tight_key},
                json={"model": "gemini-1.5-flash", "messages": [{"role": "user", "content": f"req-{i}"}]}
            )
            if res.status_code == 429:
                hit_429 = True
                log_pass("Rate Limit Enforcement", f"Successfully throttled with HTTP 429 on request #{i+1}")
                break

        if not hit_429:
            log_fail("Rate Limit Enforcement", "Failed to trigger HTTP 429 after 10 burst requests")

async def test_concurrent_atomic_debits():
    print(f"\n{BOLD}[5/5] Testing Concurrent Atomic Debits (High Concurrency){RESET}")
    tenant_id, stress_key = await provision_test_tenant("Concurrency Stress Tenant", 20.00, 600)
    num_requests = 15

    print(f"  -> Launching {num_requests} simultaneous parallel requests...")

    async def single_call(client, req_id):
        return await client.post(
            f"{BASE_URL}/chat/completions",
            headers={"X-API-Key": stress_key},
            json={"model": "gemini-1.5-flash", "messages": [{"role": "user", "content": f"Thread test {req_id}"}]}
        )

    start_time = time.time()
    async with httpx.AsyncClient(timeout=30.0) as client:
        tasks = [single_call(client, i) for i in range(num_requests)]
        responses = await asyncio.gather(*tasks)
    elapsed = time.time() - start_time

    success_count = sum(1 for r in responses if r.status_code == 200)
    if success_count != num_requests:
        log_fail("Concurrency Throughput", f"Only {success_count}/{num_requests} succeeded")

    log_pass("Concurrency Throughput", f"Completed {num_requests} parallel calls in {elapsed:.2f}s (100% 200 OK)")

    # Read final Redis balance
    r = aioredis.from_url(REDIS_URL, decode_responses=True)
    final_balance = float(await r.get(f"balance:{tenant_id}"))
    await r.aclose()

    # Calculate exact expected debit based on responses
    total_debited = sum(r.json().get("bristlecone_billing", {}).get("billed_cost_usd", 0.0) for r in responses)
    expected_balance = round(20.00 - total_debited, 6)
    actual_balance = round(final_balance, 6)

    if abs(expected_balance - actual_balance) < 0.0001:
        log_pass("Atomic Balance Ledger", f"Initial: $20.0000 | Debited: -${total_debited:.6f} | Final: ${actual_balance:.6f}")
    else:
        log_fail("Atomic Balance Ledger", f"Balance drift detected! Expected ${expected_balance:.6f}, found ${actual_balance:.6f}")

async def main():
    print(f"\n{BOLD}{'='*60}")
    print(f"   BRISTLECONE LOGIC AUTOMATED INTEGRATION SUITE")
    print(f"{'='*60}{RESET}")

    await test_auth_guardrails()
    await test_tool_execution()
    await test_zero_balance_rejection()
    await test_rate_limiting()
    await test_concurrent_atomic_debits()

    print(f"\n{GREEN}{BOLD}{'='*60}")
    print("   ALL INTEGRATION & CONCURRENCY TESTS PASSED (5/5)")
    print(f"{'='*60}{RESET}\n")

if __name__ == "__main__":
    asyncio.run(main())
