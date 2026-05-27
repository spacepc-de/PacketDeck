"""gateway telemetry dashboard fields

Revision ID: 0003_dashboard_fields
Revises: 0002_system_settings
Create Date: 2026-05-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_dashboard_fields"
down_revision: str | None = "0002_system_settings"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("gateway_telemetry", sa.Column("uptime_seconds", sa.Integer()))
    op.add_column("gateway_telemetry", sa.Column("last_rssi", sa.Numeric()))
    op.add_column("gateway_telemetry", sa.Column("last_snr", sa.Numeric()))


def downgrade() -> None:
    op.drop_column("gateway_telemetry", "last_snr")
    op.drop_column("gateway_telemetry", "last_rssi")
    op.drop_column("gateway_telemetry", "uptime_seconds")
