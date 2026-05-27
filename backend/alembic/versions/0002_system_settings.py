"""system settings

Revision ID: 0002_system_settings
Revises: 0001_initial
Create Date: 2026-05-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_system_settings"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "system_settings",
        sa.Column("key", sa.Text(), primary_key=True),
        sa.Column("value", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.execute(
        """
        INSERT INTO system_settings (key, value)
        VALUES (
            'retention',
            '{"telemetry_retention_days": 30, "node_retention_days": 90, "telemetry_poll_interval_seconds": 30}'::jsonb
        )
        ON CONFLICT (key) DO NOTHING
        """
    )


def downgrade() -> None:
    op.drop_table("system_settings")
