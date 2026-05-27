"""node repeater status metrics

Revision ID: 0006_node_repeater_stats
Revises: 0005_node_admin_credentials
Create Date: 2026-05-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_node_repeater_stats"
down_revision: str | None = "0005_node_admin_credentials"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("node_telemetry", sa.Column("noise_floor", sa.Numeric()))
    op.add_column("node_telemetry", sa.Column("uptime_seconds", sa.Integer()))
    op.add_column("node_telemetry", sa.Column("packets_received", sa.Integer()))
    op.add_column("node_telemetry", sa.Column("packets_sent", sa.Integer()))
    op.add_column("node_telemetry", sa.Column("packet_receive_errors", sa.Integer()))
    op.add_column("node_telemetry", sa.Column("tx_queue_len", sa.Integer()))
    op.add_column("node_telemetry", sa.Column("airtime", sa.Integer()))
    op.add_column("node_telemetry", sa.Column("rx_airtime", sa.Integer()))
    op.add_column("node_telemetry", sa.Column("sent_flood", sa.Integer()))
    op.add_column("node_telemetry", sa.Column("sent_direct", sa.Integer()))
    op.add_column("node_telemetry", sa.Column("recv_flood", sa.Integer()))
    op.add_column("node_telemetry", sa.Column("recv_direct", sa.Integer()))
    op.add_column("node_telemetry", sa.Column("direct_dups", sa.Integer()))
    op.add_column("node_telemetry", sa.Column("flood_dups", sa.Integer()))
    op.add_column("node_telemetry", sa.Column("full_events", sa.Integer()))


def downgrade() -> None:
    op.drop_column("node_telemetry", "full_events")
    op.drop_column("node_telemetry", "flood_dups")
    op.drop_column("node_telemetry", "direct_dups")
    op.drop_column("node_telemetry", "recv_direct")
    op.drop_column("node_telemetry", "recv_flood")
    op.drop_column("node_telemetry", "sent_direct")
    op.drop_column("node_telemetry", "sent_flood")
    op.drop_column("node_telemetry", "rx_airtime")
    op.drop_column("node_telemetry", "airtime")
    op.drop_column("node_telemetry", "tx_queue_len")
    op.drop_column("node_telemetry", "packet_receive_errors")
    op.drop_column("node_telemetry", "packets_sent")
    op.drop_column("node_telemetry", "packets_received")
    op.drop_column("node_telemetry", "uptime_seconds")
    op.drop_column("node_telemetry", "noise_floor")
