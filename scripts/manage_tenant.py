#!/usr/bin/env python3
"""
Bristlecone Logic - Tenant & API Key Administration CLI
Manage tenants, allocate initial USD balances, and generate active API keys.
"""

import sys
import os
import secrets
import hashlib
import argparse
import asyncio
from decimal import Decimal

# Ensure application modules can be imported
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sqlalchemy import text
from app.database import AsyncSessionLocal


def generate_api_key() -> tuple[str, str, str]:
    """Generate a high-entropy API key and its SHA-256 hash."""
    raw_token = secrets.token_urlsafe(32)
    api_key = f"bstk_{raw_token}"
    key_hash = hashlib.sha256(api_key.encode()).hexdigest()
    key_prefix = api_key[:10]
    return api_key, key_hash, key_prefix


async def create_tenant_async(name: str, initial_balance: float = 10.0, webhook_url: str | None = None):
    async with AsyncSessionLocal() as session:
        try:
            # 1. Insert Tenant
            insert_tenant_sql = text("""
                INSERT INTO tenants (name, credit_balance_usd, webhook_url, low_balance_threshold_usd)
                VALUES (:name, :balance, :webhook, 1.00)
                RETURNING id, name, xrpl_destination_tag, credit_balance_usd
            """)
            result = await session.execute(
                insert_tenant_sql,
                {"name": name, "balance": initial_balance, "webhook": webhook_url}
            )
            tenant = result.mappings().one()
            tenant_id = str(tenant["id"])

            # 2. Generate and Insert API Key
            raw_key, key_hash, key_prefix = generate_api_key()
            insert_key_sql = text("""
                INSERT INTO api_keys (tenant_id, name, key_prefix, key_hash, is_active)
                VALUES (:tenant_id, :name, :key_prefix, :key_hash, TRUE)
            """)
            await session.execute(
                insert_key_sql,
                {
                    "tenant_id": tenant_id,
                    "name": f"{name}-primary",
                    "key_prefix": key_prefix,
                    "key_hash": key_hash
                }
            )
            await session.commit()

            print("\n" + "=" * 65)
            print("  NEW TENANT PROVISIONED SUCCESSFULLY")
            print("=" * 65)
            print(f"  Tenant Name:      {tenant['name']}")
            print(f"  Tenant ID:        {tenant_id}")
            print(f"  Credit Balance:   ${float(tenant['credit_balance_usd']):.2f} USD")
            print(f"  XRPL Dest Tag:    {tenant['xrpl_destination_tag']}")
            print(f"  Key Prefix:       {key_prefix}...")
            print(f"  FULL API KEY:     {raw_key}")
            print("=" * 65)
            print("  Save this API key immediately. It cannot be recovered.\n")

        except Exception as e:
            await session.rollback()
            print(f"Error creating tenant: {e}")


async def list_tenants_async():
    async with AsyncSessionLocal() as session:
        try:
            # Query tenants and count of active keys
            query_sql = text("""
                SELECT 
                    t.id, 
                    t.name, 
                    t.credit_balance_usd, 
                    t.xrpl_destination_tag,
                    COUNT(k.id) FILTER (WHERE k.is_active = TRUE) as active_keys
                FROM tenants t
                LEFT JOIN api_keys k ON t.id = k.tenant_id
                GROUP BY t.id, t.name, t.credit_balance_usd, t.xrpl_destination_tag
                ORDER BY t.created_at DESC
            """)
            result = await session.execute(query_sql)
            rows = result.mappings().all()

            print("\n" + "-" * 90)
            print(f"{'Tenant ID':<38} | {'Name':<18} | {'Balance':<10} | {'XRPL Tag':<10} | {'Keys'}")
            print("-" * 90)
            for r in rows:
                bal = float(r["credit_balance_usd"] or 0.0)
                tag = r["xrpl_destination_tag"] if r["xrpl_destination_tag"] is not None else "None"
                print(f"{str(r['id']):<38} | {r['name']:<18} | ${bal:<9.2f} | {str(tag):<10} | {r['active_keys']} active")
            print("-" * 90 + "\n")

        except Exception as e:
            print(f"Error listing tenants: {e}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Bristlecone Logic Tenant Management")
    subparsers = parser.add_subparsers(dest="command")

    # Create command
    create_parser = subparsers.add_parser("create", help="Create a new tenant")
    create_parser.add_argument("name", help="Tenant name or organization")
    create_parser.add_argument("--balance", type=float, default=10.0, help="Initial USD balance (default: 10.00)")
    create_parser.add_argument("--webhook", type=str, default=None, help="Optional notification webhook URL")

    # List command
    subparsers.add_parser("list", help="List all registered tenants")

    args = parser.parse_args()

    if args.command == "create":
        asyncio.run(create_tenant_async(args.name, args.balance, args.webhook))
    elif args.command == "list":
        asyncio.run(list_tenants_async())
    else:
        parser.print_help()
