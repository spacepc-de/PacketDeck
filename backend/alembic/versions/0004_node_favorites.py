"""node favorites

Revision ID: 0004_node_favorites
Revises: 0003_dashboard_fields
Create Date: 2026-05-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_node_favorites"
down_revision: str | None = "0003_dashboard_fields"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "nodes",
        sa.Column("is_favorite", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )
    op.create_index("ix_nodes_favorite_last_heard", "nodes", ["is_favorite", "last_heard_at"])


def downgrade() -> None:
    op.drop_index("ix_nodes_favorite_last_heard", table_name="nodes")
    op.drop_column("nodes", "is_favorite")
