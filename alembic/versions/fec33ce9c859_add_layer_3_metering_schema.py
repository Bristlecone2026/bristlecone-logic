"""add_layer_3_metering_schema

Revision ID: fec33ce9c859
Revises: 
Create Date: 2026-07-30
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'fec33ce9c859'
down_revision = '60962c26fe50'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create tenants table
    op.create_table(
        'tenants',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
        sa.Column('credit_balance_usd', sa.Numeric(precision=12, scale=6), server_default=sa.text('0.000000'), nullable=False),
        sa.Column('rate_limit_rpm', sa.Integer(), server_default=sa.text('60'), nullable=False),
        sa.Column('custom_llm_key', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )

    # 2. Create api_keys table
    op.create_table(
        'api_keys',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('tenant_id', sa.UUID(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('key_prefix', sa.String(length=16), nullable=False),
        sa.Column('key_hash', sa.String(length=64), nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
        sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('key_hash')
    )
    op.create_index('idx_api_keys_hash', 'api_keys', ['key_hash'], unique=False)

    # 3. Create llm_usage_ledger table
    op.create_table(
        'llm_usage_ledger',
        sa.Column('id', sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column('tenant_id', sa.UUID(), nullable=False),
        sa.Column('api_key_id', sa.UUID(), nullable=True),
        sa.Column('model_requested', sa.String(length=100), nullable=False),
        sa.Column('provider', sa.String(length=50), nullable=False),
        sa.Column('is_byok', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('input_tokens', sa.Integer(), server_default=sa.text('0'), nullable=False),
        sa.Column('output_tokens', sa.Integer(), server_default=sa.text('0'), nullable=False),
        sa.Column('total_tokens', sa.Integer(), server_default=sa.text('0'), nullable=False),
        sa.Column('raw_cost_usd', sa.Numeric(precision=12, scale=6), server_default=sa.text('0.000000'), nullable=False),
        sa.Column('billed_cost_usd', sa.Numeric(precision=12, scale=6), server_default=sa.text('0.000000'), nullable=False),
        sa.Column('latency_ms', sa.Integer(), nullable=True),
        sa.Column('status_code', sa.Integer(), server_default=sa.text('200'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.ForeignKeyConstraint(['api_key_id'], ['api_keys.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_ledger_tenant_time', 'llm_usage_ledger', ['tenant_id', sa.text('created_at DESC')], unique=False)


def downgrade() -> None:
    op.drop_index('idx_ledger_tenant_time', table_name='llm_usage_ledger')
    op.drop_table('llm_usage_ledger')
    op.drop_index('idx_api_keys_hash', table_name='api_keys')
    op.drop_table('api_keys')
    op.drop_table('tenants')
