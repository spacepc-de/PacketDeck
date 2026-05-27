"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-05-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def uuid_pk() -> sa.Column:
    return sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()"))


def timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    ]


def upgrade() -> None:
    op.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto"')

    op.create_table(
        "devices",
        uuid_pk(),
        sa.Column("name", sa.Text()),
        sa.Column("connection_type", sa.Text(), nullable=False, server_default="serial"),
        sa.Column("serial_port", sa.Text()),
        sa.Column("serial_baud", sa.Integer()),
        sa.Column("ble_address", sa.Text()),
        sa.Column("firmware_version", sa.Text()),
        sa.Column("hardware_model", sa.Text()),
        sa.Column("raw_info", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        *timestamps(),
    )
    op.create_table(
        "connection_profiles",
        uuid_pk(),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("serial_port", sa.Text()),
        sa.Column("serial_baud", sa.Integer()),
        sa.Column("ble_address", sa.Text()),
        sa.Column("ble_pin_secret_ref", sa.Text()),
        sa.Column("auto_reconnect", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        *timestamps(),
    )
    op.create_table(
        "gateway_telemetry",
        uuid_pk(),
        sa.Column("device_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("devices.id", ondelete="SET NULL")),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("bandwidth_khz", sa.Numeric()),
        sa.Column("battery_percentage", sa.Numeric()),
        sa.Column("battery_voltage_v", sa.Numeric()),
        sa.Column("ch1_voltage_v", sa.Numeric()),
        sa.Column("companion_prefix", sa.Text()),
        sa.Column("frequency_mhz", sa.Numeric()),
        sa.Column("last_message_delivery", sa.Text()),
        sa.Column("latitude", sa.Numeric()),
        sa.Column("longitude", sa.Numeric()),
        sa.Column("node_count", sa.Integer()),
        sa.Column("node_status", sa.Text()),
        sa.Column("request_rate_limiter_tokens", sa.Numeric()),
        sa.Column("spreading_factor", sa.Integer()),
        sa.Column("tx_power_dbm", sa.Numeric()),
        sa.Column("source", sa.Text(), nullable=False, server_default="event"),
        sa.Column("raw_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
    )
    op.create_index("ix_gateway_telemetry_device_recorded", "gateway_telemetry", ["device_id", sa.text("recorded_at DESC")])
    op.create_index("ix_gateway_telemetry_recorded", "gateway_telemetry", [sa.text("recorded_at DESC")])

    op.create_table(
        "nodes",
        uuid_pk(),
        sa.Column("meshcore_id", sa.Text(), nullable=False),
        sa.Column("public_key", sa.Text()),
        sa.Column("short_name", sa.Text()),
        sa.Column("long_name", sa.Text()),
        sa.Column("display_name", sa.Text()),
        sa.Column("role", sa.Text()),
        sa.Column("status", sa.Text(), nullable=False, server_default="unknown"),
        sa.Column("first_seen_at", sa.DateTime(timezone=True)),
        sa.Column("last_heard_at", sa.DateTime(timezone=True)),
        sa.Column("latitude", sa.Numeric()),
        sa.Column("longitude", sa.Numeric()),
        sa.Column("altitude", sa.Numeric()),
        sa.Column("battery_percentage", sa.Numeric()),
        sa.Column("battery_voltage_v", sa.Numeric()),
        sa.Column("firmware_version", sa.Text()),
        sa.Column("hardware_model", sa.Text()),
        sa.Column("raw_info", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        *timestamps(),
    )
    op.create_index("ix_nodes_meshcore_id", "nodes", ["meshcore_id"])
    op.create_index("ix_nodes_public_key", "nodes", ["public_key"])
    op.create_index("ix_nodes_status_last_heard", "nodes", ["status", sa.text("last_heard_at DESC")])

    op.create_table(
        "node_telemetry",
        uuid_pk(),
        sa.Column("node_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("nodes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("latitude", sa.Numeric()),
        sa.Column("longitude", sa.Numeric()),
        sa.Column("altitude", sa.Numeric()),
        sa.Column("battery_percentage", sa.Numeric()),
        sa.Column("battery_voltage_v", sa.Numeric()),
        sa.Column("rssi", sa.Numeric()),
        sa.Column("snr", sa.Numeric()),
        sa.Column("hops", sa.Integer()),
        sa.Column("raw_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
    )
    op.create_index("ix_node_telemetry_node_recorded", "node_telemetry", ["node_id", sa.text("recorded_at DESC")])
    op.create_index("ix_node_telemetry_recorded", "node_telemetry", [sa.text("recorded_at DESC")])

    op.create_table(
        "node_events",
        uuid_pk(),
        sa.Column("node_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("nodes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("event_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "messages",
        uuid_pk(),
        sa.Column("direction", sa.Text(), nullable=False),
        sa.Column("message_type", sa.Text(), nullable=False, server_default="text"),
        sa.Column("from_node_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("nodes.id", ondelete="SET NULL")),
        sa.Column("to_node_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("nodes.id", ondelete="SET NULL")),
        sa.Column("channel", sa.Text()),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="unknown"),
        sa.Column("delivery_state", sa.Text()),
        sa.Column("expected_ack", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("meshcore_message_id", sa.Text()),
        sa.Column("received_at", sa.DateTime(timezone=True)),
        sa.Column("sent_at", sa.DateTime(timezone=True)),
        sa.Column("delivered_at", sa.DateTime(timezone=True)),
        sa.Column("raw_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
    )
    op.create_index("ix_messages_from_received", "messages", ["from_node_id", sa.text("received_at DESC")])
    op.create_index("ix_messages_to_sent", "messages", ["to_node_id", sa.text("sent_at DESC")])
    op.create_index("ix_messages_direction_received", "messages", ["direction", sa.text("received_at DESC")])

    op.create_table("automation_rules", uuid_pk(), sa.Column("name", sa.Text(), nullable=False), sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")), sa.Column("trigger_type", sa.Text(), nullable=False), sa.Column("trigger_config", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")), sa.Column("conditions", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")), sa.Column("actions", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")), sa.Column("cooldown_seconds", sa.Integer(), nullable=False, server_default="0"), *timestamps())
    op.create_table("automation_runs", uuid_pk(), sa.Column("rule_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("automation_rules.id", ondelete="CASCADE")), sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()), sa.Column("finished_at", sa.DateTime(timezone=True)), sa.Column("status", sa.Text(), nullable=False), sa.Column("trigger_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")), sa.Column("action_results", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")), sa.Column("error_message", sa.Text()))
    op.create_table("mqtt_brokers", uuid_pk(), sa.Column("name", sa.Text(), nullable=False), sa.Column("host", sa.Text(), nullable=False), sa.Column("port", sa.Integer(), nullable=False, server_default="1883"), sa.Column("username", sa.Text()), sa.Column("password_secret_ref", sa.Text()), sa.Column("tls_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")), sa.Column("client_id", sa.Text()), sa.Column("topic_prefix", sa.Text(), nullable=False, server_default="meshcore-webgui"), sa.Column("retain_settings", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")), *timestamps())
    op.create_table("webhook_targets", uuid_pk(), sa.Column("name", sa.Text(), nullable=False), sa.Column("url", sa.Text(), nullable=False), sa.Column("secret_ref", sa.Text()), sa.Column("headers", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")), *timestamps())
    op.create_table("api_tokens", uuid_pk(), sa.Column("name", sa.Text(), nullable=False), sa.Column("token_hash", sa.Text(), nullable=False), sa.Column("last_used_at", sa.DateTime(timezone=True)), *timestamps())
    op.create_table("device_settings_history", uuid_pk(), sa.Column("device_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("devices.id", ondelete="CASCADE")), sa.Column("setting_key", sa.Text(), nullable=False), sa.Column("old_value", postgresql.JSONB(astext_type=sa.Text())), sa.Column("new_value", postgresql.JSONB(astext_type=sa.Text())), sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()), sa.Column("source", sa.Text(), nullable=False, server_default="api"))
    op.create_table("system_events", uuid_pk(), sa.Column("event_type", sa.Text(), nullable=False), sa.Column("severity", sa.Text(), nullable=False, server_default="info"), sa.Column("message", sa.Text(), nullable=False), sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))


def downgrade() -> None:
    for table in [
        "system_events",
        "device_settings_history",
        "api_tokens",
        "webhook_targets",
        "mqtt_brokers",
        "automation_runs",
        "automation_rules",
        "messages",
        "node_events",
        "node_telemetry",
        "nodes",
        "gateway_telemetry",
        "connection_profiles",
        "devices",
    ]:
        op.drop_table(table)
