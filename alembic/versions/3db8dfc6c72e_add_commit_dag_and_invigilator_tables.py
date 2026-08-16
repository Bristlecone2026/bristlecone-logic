"""add_commit_dag_and_invigilator_tables

Revision ID: 3db8dfc6c72e
Revises: 98192c389c24
Create Date: 2026-07-28 13:09:26.774958
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = '3db8dfc6c72e'
down_revision: Union[str, None] = '98192c389c24'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
