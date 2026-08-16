#!/usr/bin/env python3
import asyncio
import os
import sys
import uuid
import hashlib
import secrets
import argparse
from decimal import Decimal
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text
import redis.asyncio as aioredis

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@db:5432/bristlecone_db")
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")

engine = create_async_engine(DATABASE_URL)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

async def list_tenants():
    async with AsyncSessionLocal() as session:
        result = await session.execute(text("""
            SELECT t.id, t.name, t.credit_balance_usd, t.rate_limit_rpm, t.is_active, 
                   t.xrpl_destination_tag, COUNT(k.id) as key_count
            FROM tenants t
            LEFT JOIN api_keys k ON t.id = k.tenant_id AND k.is_active = true
            GROUP BY t.id
            ORDER BY t.created_at ASC;
        """))
        rows = result.fetchall()

        print("\n" + "=" * 105)
        print(f"{'ID':<38} {'Name':<24} {'Balance':<10} {'RPM':<6} {'XRPL Tag':<10} {'Keys':<5}")
        print("-" * 105)
        for r in rows:
            tag_str = str(r[5]) if r[5] else "N/A"
            print(f"{str(r[0]):<38} {r[1]:<24} ${float(r[2]):<9.4f} {r[3]:<6} {tag_str:<10} {r[6]:<5}")
        print("=" * 105 + "\n")

async def create_tenant(name: str, balance: float, rate_limit: int, threshold: float, webhook: str):
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text("""
                INSERT INTO tenants (
                    name, credit_balance_usd, rate_limit_rpm, low_balance_threshold_usd, webhook_url, xrpl_destination_tag
                ) VALUES (
                    :name, :balance, :rate_limit, :threshold, :webhook, nextval('xrpl_destination_tag_seq')
                ) RETURNING id, xrpl_destination_tag;
            """),
            {
                "name": name,
                "balance": Decimal(str(balance)),
                "rate_limit": rate_limit,
                "threshold": Decimal(str(threshold)),
                "webhook": webhook
            }
        )
        row = result.first()
        tenant_id, xrpl_tag = row[0], row[1]
        await session.commit()

        redis_client = aioredis.from_url(REDIS_URL)
        await redis_client.set(f"balance:{tenant_id}", float(balance))
        await redis_client.aclose()

        print("\n=== Tenant Provisioned Successfully ===")
        print(f"Tenant ID:            {tenant_id}")
        print(f"Name:                 {name}")
        print(f"Initial Balance:      ${balance:.2f} USD")
        print(f"Rate Limit:           {rate_limit} RPM")
        print(f"XRPL Destination Tag: {xrpl_tag}")
        print(f"Alert Threshold:      ${threshold:.2f} USD")
        print("========================================\n")

async def create_key(tenant_id_str: str, key_name: str):
    try:
        tenant_id = uuid.UUID(tenant_id_str)
    except ValueError:
        print(f"Error: Invalid UUID format '{tenant_id_str}'")
        sys.exit(1)

    raw_token = f"bstk_{secrets.token_urlsafe(32)}"
    key_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    key_prefix = raw_token[:8]

    async with AsyncSessionLocal() as session:
        res = await session.execute(
            text("SELECT name FROM tenants WHERE id = :id"),
            {"id": tenant_id}
        )
        if not res.first():
            print(f"Error: Tenant {tenant_id} does not exist.")
            return

        await session.execute(
            text("""
                INSERT INTO api_keys (tenant_id, name, key_hash, key_prefix, is_active)
                VALUES (:tenant_id, :name, :key_hash, :key_prefix, true)
            """),
            {
                "tenant_id": tenant_id,
                "name": key_name,
                "key_hash": key_hash,
                "key_prefix": key_prefix
            }
        )
        await session.commit()

        print("\n=== API Key Provisioned ===")
        print(f"Tenant ID:   {tenant_id}")
        print(f"Key Name:    {key_name}")
        print(f"Key Prefix:  {key_prefix}...")
        print(f"Secret Key:  {raw_token}")
        print("---------------------------------------------------------")
        print("STORE THIS SECRET KEY NOW. It cannot be retrieved again.")
        print("=========================================================\n")

async def metrics():
    async with AsyncSessionLocal() as session:
        dep_res = await session.execute(text("SELECT COALESCE(SUM(usd_value), 0), COUNT(*) FROM tenant_deposits WHERE status = 'confirmed'"))
        dep_row = dep_res.first()
        
        usage_res = await session.execute(text("SELECT COALESCE(SUM(billed_cost_usd), 0), COALESCE(SUM(total_tokens), 0), COUNT(*) FROM llm_usage_ledger"))
        usage_row = usage_res.first()

        print("\n" + "=" * 50)
        print("         BRISTLECONE LOGIC PLATFORM METRICS       ")
        print("=" * 50)
        print(f"Total Confirmed Deposits:     ${float(dep_row[0]):.2f} ({dep_row[1]} txs)")
        print(f"Total Invoiced Usage Revenue: ${float(usage_row[0]):.6f}")
        print(f"Total API Invocations:        {usage_row[2]}")
        print(f"Total Tokens Routed:          {usage_row[1]:,}")
        print("=" * 50 + "\n")

def main():
    parser = argparse.ArgumentParser(description="Bristlecone Logic Management CLI")
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("list-tenants")
    subparsers.add_parser("metrics")

    create_t_parser = subparsers.add_parser("create-tenant")
    create_t_parser.add_argument("--name", required=True, help="Tenant Name")
    create_t_parser.add_argument("--balance", type=float, default=0.0, help="Initial USD balance")
    create_t_parser.add_argument("--rate-limit", type=int, default=60, help="Rate limit RPM")
    create_t_parser.add_argument("--threshold", type=float, default=1.0, help="Low balance threshold")
    create_t_parser.add_argument("--webhook-url", default=None, help="Webhook URL")

    create_k_parser = subparsers.add_parser("create-key")
    create_k_parser.add_argument("--tenant-id", required=True, help="Tenant UUID")
    create_k_parser.add_argument("--name", default="Default Key", help="Key identifier")

    args = parser.parse_args()

    if args.command == "list-tenants":
        asyncio.run(list_tenants())
    elif args.command == "create-tenant":
        asyncio.run(create_tenant(args.name, args.balance, args.rate_limit, args.threshold, args.webhook_url))
    elif args.command == "create-key":
        asyncio.run(create_key(args.tenant_id, args.name))
    elif args.command == "metrics":
        asyncio.run(metrics())
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
