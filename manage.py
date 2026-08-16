#!/usr/bin/env python3
import asyncio
import os
import sys
import uuid
import secrets
import hashlib
import argparse
from decimal import Decimal
from sqlalchemy import text
import redis.asyncio as aioredis

from app.database import AsyncSessionLocal

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")

def hash_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()

def generate_api_key() -> tuple[str, str, str]:
    raw_token = secrets.token_urlsafe(32)
    raw_key = f"bl_live_{raw_token}"
    prefix = raw_key[:12]
    key_hash = hash_key(raw_key)
    return raw_key, prefix, key_hash

async def create_tenant(name: str, balance: float, rate_limit: int, threshold: float, webhook_url: str = None):
    async with AsyncSessionLocal() as session:
        tenant_id = uuid.uuid4()
        await session.execute(
            text("""
                INSERT INTO tenants (id, name, is_active, credit_balance_usd, rate_limit_rpm, low_balance_threshold_usd, webhook_url)
                VALUES (:id, :name, true, :balance, :rate_limit, :threshold, :webhook_url)
            """),
            {
                "id": tenant_id,
                "name": name,
                "balance": Decimal(str(balance)),
                "rate_limit": rate_limit,
                "threshold": Decimal(str(threshold)),
                "webhook_url": webhook_url
            }
        )
        await session.commit()

        try:
            r = aioredis.from_url(REDIS_URL, decode_responses=True)
            await r.set(f"balance:{tenant_id}", str(balance))
            await r.aclose()
        except Exception as e:
            print(f"[Warning] Redis sync: {e}")

        print("\n=== Tenant Provisioned Successfully ===")
        print(f"Tenant ID:           {tenant_id}")
        print(f"Name:                {name}")
        print(f"Initial Balance:     ${balance:.2f} USD")
        print(f"Rate Limit:          {rate_limit} RPM")
        print(f"Alert Threshold:     ${threshold:.2f} USD")
        print("========================================\n")
        return tenant_id

async def create_key(tenant_id_str: str, key_name: str):
    tenant_id = uuid.UUID(tenant_id_str)
    raw_key, prefix, key_hash = generate_api_key()

    async with AsyncSessionLocal() as session:
        res = await session.execute(text("SELECT name FROM tenants WHERE id = :tid"), {"tid": tenant_id})
        tenant = res.first()
        if not tenant:
            print(f"Error: Tenant '{tenant_id}' not found.")
            return

        key_id = uuid.uuid4()
        await session.execute(
            text("""
                INSERT INTO api_keys (id, tenant_id, name, key_prefix, key_hash, prefix, is_active)
                VALUES (:id, :tenant_id, :name, :prefix, :key_hash, :prefix, true)
            """),
            {
                "id": key_id,
                "tenant_id": tenant_id,
                "name": key_name,
                "prefix": prefix,
                "key_hash": key_hash
            }
        )
        await session.commit()

        print("\n=== API Key Generated Successfully ===")
        print(f"Tenant:      {tenant[0]} ({tenant_id})")
        print(f"Key Name:    {key_name}")
        print(f"Key Prefix:  {prefix}...")
        print(f"API Key:     {raw_key}")
        print("=======================================\n")
        return raw_key

async def list_tenants():
    async with AsyncSessionLocal() as session:
        query = text("""
            SELECT 
                t.id, 
                t.name, 
                t.credit_balance_usd, 
                t.rate_limit_rpm, 
                t.is_active,
                COUNT(k.id) AS key_count
            FROM tenants t
            LEFT JOIN api_keys k ON t.id = k.tenant_id AND k.is_active = true
            GROUP BY t.id
            ORDER BY t.created_at ASC;
        """)
        res = await session.execute(query)
        rows = res.fetchall()

        print("\n" + "=" * 90)
        print(f"{'ID':<38} {'Name':<24} {'Balance':<12} {'RPM':<6} {'Active':<8} {'Keys'}")
        print("-" * 90)
        for r in rows:
            print(f"{str(r[0]):<38} {r[1]:<24} ${float(r[2]):<11.4f} {r[3]:<6} {str(r[4]):<8} {r[5]}")
        print("=" * 90 + "\n")

async def platform_metrics():
    async with AsyncSessionLocal() as session:
        dep_res = await session.execute(text("SELECT COALESCE(SUM(amount_usdc), 0), COUNT(*) FROM tenant_deposits WHERE status = 'confirmed'"))
        total_deposits, dep_count = dep_res.first()

        usage_res = await session.execute(text("""
            SELECT 
                COUNT(*),
                COALESCE(SUM(billed_cost_usd), 0),
                COALESCE(SUM(total_tokens), 0)
            FROM llm_usage_ledger;
        """))
        total_calls, billed_rev, total_tokens = usage_res.first()

        print("\n" + "=" * 50)
        print("         BRISTLECONE LOGIC PLATFORM METRICS       ")
        print("=" * 50)
        print(f"Total Confirmed USDC Deposits:  ${float(total_deposits):.2f} ({dep_count} txs)")
        print(f"Total Invoiced Usage Revenue:   ${float(billed_rev):.6f}")
        print(f"Total API Invocations Metered:  {total_calls}")
        print(f"Total LLM Tokens Routed:        {total_tokens:,}")
        print("=" * 50 + "\n")

def main():
    parser = argparse.ArgumentParser(description="Bristlecone Logic Management CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # create-tenant
    p_tenant = subparsers.add_parser("create-tenant", help="Provision a new tenant")
    p_tenant.add_argument("--name", required=True)
    p_tenant.add_argument("--balance", type=float, default=10.0)
    p_tenant.add_argument("--rate-limit", type=int, default=120)
    p_tenant.add_argument("--threshold", type=float, default=1.0)
    p_tenant.add_argument("--webhook-url", default=None)

    # create-key
    p_key = subparsers.add_parser("create-key", help="Generate an API key for a tenant")
    p_key.add_argument("--tenant-id", required=True)
    p_key.add_argument("--name", default="Default Key")

    # list-tenants
    subparsers.add_parser("list-tenants")

    # metrics
    subparsers.add_parser("metrics")

    args = parser.parse_args()

    if args.command == "create-tenant":
        asyncio.run(create_tenant(args.name, args.balance, args.rate_limit, args.threshold, args.webhook_url))
    elif args.command == "create-key":
        asyncio.run(create_key(args.tenant_id, args.name))
    elif args.command == "list-tenants":
        asyncio.run(list_tenants())
    elif args.command == "metrics":
        asyncio.run(platform_metrics())

if __name__ == "__main__":
    main()
