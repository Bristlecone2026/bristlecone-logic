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
    # 1. Drop organization slug if intended
    # # op.drop_column('organizations', 'slug')
    
    # 2. Add title as nullable first so existing rows don't violate constraints
    op.add_column('projects', sa.Column('title', sa.String(length=255), nullable=True))
    
    # 3. Backfill title from existing name data
    op.execute("UPDATE projects SET title = name WHERE title IS NULL")
    
    # 4. Fallback for any rows where both were null
    op.execute("UPDATE projects SET title = 'Untitled Project' WHERE title IS NULL")
    
    # 5. Alter title to NOT NULL now that data is populated
    op.alter_column('projects', 'title', existing_type=sa.String(length=255), nullable=False)
    
    # 6. Drop the old name column
    op.drop_column('projects', 'name')

    # Note: Commit DAG and Invigilator tables will be added if they were part of your models. 
    # If they weren't auto-generated because they reside in app/models/dag.py, ensure they are imported in app/models/__init__.py so Alembic picks them up.


def downgrade() -> None:
    op.add_column('projects', sa.Column('name', sa.VARCHAR(), autoincrement=False, nullable=True))
    op.execute("UPDATE projects SET name = title WHERE name IS NULL")
    op.drop_column('projects', 'title')
    op.add_column('organizations', sa.Column('slug', sa.VARCHAR(), autoincrement=False, nullable=True))
