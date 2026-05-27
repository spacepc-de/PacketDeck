"""node admin credentials

Revision ID: 0005_node_admin_credentials
Revises: 0004_node_favorites
Create Date: 2026-05-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005_node_admin_credentials"
down_revision: str | None = "0004_node_favorites"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "node_admin_credentials",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("node_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("admin_password", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["node_id"], ["nodes.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_node_admin_credentials_node_id",
        "node_admin_credentials",
        ["node_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_node_admin_credentials_node_id", table_name="node_admin_credentials")
    op.drop_table("node_admin_credentials")
