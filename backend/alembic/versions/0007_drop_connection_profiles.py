"""drop unused connection profiles

Revision ID: 0007_drop_connection_profiles
Revises: 0006_node_repeater_stats
Create Date: 2026-05-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007_drop_connection_profiles"
down_revision: str | None = "0006_node_repeater_stats"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_table("connection_profiles")


def downgrade() -> None:
    op.create_table(
        "connection_profiles",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("serial_port", sa.Text(), nullable=True),
        sa.Column("serial_baud", sa.Integer(), nullable=True),
        sa.Column("ble_address", sa.Text(), nullable=True),
        sa.Column("ble_pin_secret_ref", sa.Text(), nullable=True),
        sa.Column("auto_reconnect", sa.Boolean(), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
