import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, Numeric, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class Device(Base, TimestampMixin):
    __tablename__ = "devices"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str | None] = mapped_column(Text)
    connection_type: Mapped[str] = mapped_column(Text, default="serial")
    serial_port: Mapped[str | None] = mapped_column(Text)
    serial_baud: Mapped[int | None] = mapped_column(Integer)
    ble_address: Mapped[str | None] = mapped_column(Text)
    firmware_version: Mapped[str | None] = mapped_column(Text)
    hardware_model: Mapped[str | None] = mapped_column(Text)
    raw_info: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)


class GatewayTelemetry(Base):
    __tablename__ = "gateway_telemetry"
    __table_args__ = (
        Index("ix_gateway_telemetry_device_recorded", "device_id", "recorded_at"),
        Index("ix_gateway_telemetry_recorded", "recorded_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    device_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("devices.id", ondelete="SET NULL"))
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    bandwidth_khz: Mapped[Decimal | None] = mapped_column(Numeric)
    battery_percentage: Mapped[Decimal | None] = mapped_column(Numeric)
    battery_voltage_v: Mapped[Decimal | None] = mapped_column(Numeric)
    ch1_voltage_v: Mapped[Decimal | None] = mapped_column(Numeric)
    companion_prefix: Mapped[str | None] = mapped_column(Text)
    frequency_mhz: Mapped[Decimal | None] = mapped_column(Numeric)
    last_message_delivery: Mapped[str | None] = mapped_column(Text)
    latitude: Mapped[Decimal | None] = mapped_column(Numeric)
    longitude: Mapped[Decimal | None] = mapped_column(Numeric)
    node_count: Mapped[int | None] = mapped_column(Integer)
    node_status: Mapped[str | None] = mapped_column(Text)
    request_rate_limiter_tokens: Mapped[Decimal | None] = mapped_column(Numeric)
    spreading_factor: Mapped[int | None] = mapped_column(Integer)
    tx_power_dbm: Mapped[Decimal | None] = mapped_column(Numeric)
    uptime_seconds: Mapped[int | None] = mapped_column(Integer)
    last_rssi: Mapped[Decimal | None] = mapped_column(Numeric)
    last_snr: Mapped[Decimal | None] = mapped_column(Numeric)
    source: Mapped[str] = mapped_column(Text, default="event")
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)


class Node(Base, TimestampMixin):
    __tablename__ = "nodes"
    __table_args__ = (
        Index("ix_nodes_meshcore_id", "meshcore_id"),
        Index("ix_nodes_public_key", "public_key"),
        Index("ix_nodes_status_last_heard", "status", "last_heard_at"),
        Index("ix_nodes_favorite_last_heard", "is_favorite", "last_heard_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    meshcore_id: Mapped[str] = mapped_column(Text)
    public_key: Mapped[str | None] = mapped_column(Text)
    short_name: Mapped[str | None] = mapped_column(Text)
    long_name: Mapped[str | None] = mapped_column(Text)
    display_name: Mapped[str | None] = mapped_column(Text)
    is_favorite: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    role: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, default="unknown")
    first_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_heard_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    latitude: Mapped[Decimal | None] = mapped_column(Numeric)
    longitude: Mapped[Decimal | None] = mapped_column(Numeric)
    altitude: Mapped[Decimal | None] = mapped_column(Numeric)
    battery_percentage: Mapped[Decimal | None] = mapped_column(Numeric)
    battery_voltage_v: Mapped[Decimal | None] = mapped_column(Numeric)
    firmware_version: Mapped[str | None] = mapped_column(Text)
    hardware_model: Mapped[str | None] = mapped_column(Text)
    raw_info: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)


class NodeAdminCredential(Base, TimestampMixin):
    __tablename__ = "node_admin_credentials"
    __table_args__ = (Index("ix_node_admin_credentials_node_id", "node_id", unique=True),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    node_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("nodes.id", ondelete="CASCADE"),
    )
    admin_password: Mapped[str] = mapped_column(Text)


class NodeTelemetry(Base):
    __tablename__ = "node_telemetry"
    __table_args__ = (
        Index("ix_node_telemetry_node_recorded", "node_id", "recorded_at"),
        Index("ix_node_telemetry_recorded", "recorded_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    node_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("nodes.id", ondelete="CASCADE"))
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    latitude: Mapped[Decimal | None] = mapped_column(Numeric)
    longitude: Mapped[Decimal | None] = mapped_column(Numeric)
    altitude: Mapped[Decimal | None] = mapped_column(Numeric)
    battery_percentage: Mapped[Decimal | None] = mapped_column(Numeric)
    battery_voltage_v: Mapped[Decimal | None] = mapped_column(Numeric)
    rssi: Mapped[Decimal | None] = mapped_column(Numeric)
    snr: Mapped[Decimal | None] = mapped_column(Numeric)
    noise_floor: Mapped[Decimal | None] = mapped_column(Numeric)
    hops: Mapped[int | None] = mapped_column(Integer)
    uptime_seconds: Mapped[int | None] = mapped_column(Integer)
    packets_received: Mapped[int | None] = mapped_column(Integer)
    packets_sent: Mapped[int | None] = mapped_column(Integer)
    packet_receive_errors: Mapped[int | None] = mapped_column(Integer)
    tx_queue_len: Mapped[int | None] = mapped_column(Integer)
    airtime: Mapped[int | None] = mapped_column(Integer)
    rx_airtime: Mapped[int | None] = mapped_column(Integer)
    sent_flood: Mapped[int | None] = mapped_column(Integer)
    sent_direct: Mapped[int | None] = mapped_column(Integer)
    recv_flood: Mapped[int | None] = mapped_column(Integer)
    recv_direct: Mapped[int | None] = mapped_column(Integer)
    direct_dups: Mapped[int | None] = mapped_column(Integer)
    flood_dups: Mapped[int | None] = mapped_column(Integer)
    full_events: Mapped[int | None] = mapped_column(Integer)
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)


class NodeEvent(Base):
    __tablename__ = "node_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    node_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("nodes.id", ondelete="CASCADE"))
    event_type: Mapped[str] = mapped_column(Text)
    event_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (
        Index("ix_messages_from_received", "from_node_id", "received_at"),
        Index("ix_messages_to_sent", "to_node_id", "sent_at"),
        Index("ix_messages_direction_received", "direction", "received_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    direction: Mapped[str] = mapped_column(Text)
    message_type: Mapped[str] = mapped_column(Text, default="text")
    from_node_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("nodes.id", ondelete="SET NULL"))
    to_node_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("nodes.id", ondelete="SET NULL"))
    channel: Mapped[str | None] = mapped_column(Text)
    body: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, default="unknown")
    delivery_state: Mapped[str | None] = mapped_column(Text)
    expected_ack: Mapped[bool] = mapped_column(Boolean, default=True)
    meshcore_message_id: Mapped[str | None] = mapped_column(Text)
    received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)


class AutomationRule(Base, TimestampMixin):
    __tablename__ = "automation_rules"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    trigger_type: Mapped[str] = mapped_column(Text)
    trigger_config: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    conditions: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    actions: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    cooldown_seconds: Mapped[int] = mapped_column(Integer, default=0)


class AutomationRun(Base):
    __tablename__ = "automation_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    rule_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("automation_rules.id", ondelete="CASCADE"))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(Text)
    trigger_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    action_results: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    error_message: Mapped[str | None] = mapped_column(Text)


class MqttBroker(Base, TimestampMixin):
    __tablename__ = "mqtt_brokers"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(Text)
    host: Mapped[str] = mapped_column(Text)
    port: Mapped[int] = mapped_column(Integer, default=1883)
    username: Mapped[str | None] = mapped_column(Text)
    password_secret_ref: Mapped[str | None] = mapped_column(Text)
    tls_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    client_id: Mapped[str | None] = mapped_column(Text)
    topic_prefix: Mapped[str] = mapped_column(Text, default="meshcore-webgui")
    retain_settings: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)


class WebhookTarget(Base, TimestampMixin):
    __tablename__ = "webhook_targets"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(Text)
    url: Mapped[str] = mapped_column(Text)
    secret_ref: Mapped[str | None] = mapped_column(Text)
    headers: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)


class ApiToken(Base, TimestampMixin):
    __tablename__ = "api_tokens"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(Text)
    token_hash: Mapped[str] = mapped_column(Text)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class DeviceSettingsHistory(Base):
    __tablename__ = "device_settings_history"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    device_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("devices.id", ondelete="CASCADE"))
    setting_key: Mapped[str] = mapped_column(Text)
    old_value: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    new_value: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    source: Mapped[str] = mapped_column(Text, default="api")


class SystemEvent(Base):
    __tablename__ = "system_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_type: Mapped[str] = mapped_column(Text)
    severity: Mapped[str] = mapped_column(Text, default="info")
    message: Mapped[str] = mapped_column(Text)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SystemSetting(Base, TimestampMixin):
    __tablename__ = "system_settings"

    key: Mapped[str] = mapped_column(Text, primary_key=True)
    value: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
