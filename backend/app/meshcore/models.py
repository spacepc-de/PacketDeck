from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

ConnectionMode = Literal["tcp"]
ConnectionStateValue = Literal["disconnected", "connecting", "connected", "reconnecting", "error"]


class ConnectionState(BaseModel):
    state: ConnectionStateValue = "disconnected"
    connection_type: ConnectionMode
    device_identifier: str | None = None
    last_connected_at: datetime | None = None
    last_disconnected_at: datetime | None = None
    last_error: str | None = None
    reconnect_attempt_count: int = 0
    api_library_version: str | None = None
    firmware_version: str | None = None


class DeviceSetting(BaseModel):
    key: str
    label: str
    category: str
    value: Any = None
    unit: str | None = None
    editable: bool = False
    available: bool = True
    min_value: float | None = None
    max_value: float | None = None
    options: list[dict[str, Any]] | None = None
    description: str | None = None


class DeviceSettingsPatch(BaseModel):
    values: dict[str, Any]


class MessageSendRequest(BaseModel):
    to_node_id: str | None = None
    body: str = Field(min_length=1, max_length=4096)
    channel: str | None = None
    expect_ack: bool = True

    @model_validator(mode="after")
    def require_destination(self):
        if not self.to_node_id and self.channel in (None, ""):
            raise ValueError("Either to_node_id or channel is required")
        return self
