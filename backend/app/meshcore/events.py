from datetime import UTC, datetime
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field


MeshCoreEventType = Literal[
    "connection.status_changed",
    "device.info_updated",
    "device.settings_updated",
    "telemetry.gateway_updated",
    "telemetry.node_updated",
    "node.discovered",
    "node.updated",
    "node.status_changed",
    "message.received",
    "message.sent",
    "message.delivery_updated",
    "system.error",
]


class MeshCoreEvent(BaseModel):
    type: MeshCoreEventType
    payload: dict[str, Any] = Field(default_factory=dict)
    source: str = "meshcore"
    severity: str = "info"
