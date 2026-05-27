from abc import ABC, abstractmethod
from collections.abc import AsyncIterator

from app.meshcore.events import MeshCoreEvent


class MeshCoreTransport(ABC):
    @abstractmethod
    async def connect(self) -> None:
        raise NotImplementedError

    @abstractmethod
    async def disconnect(self) -> None:
        raise NotImplementedError

    @abstractmethod
    async def events(self) -> AsyncIterator[MeshCoreEvent]:
        raise NotImplementedError

    @abstractmethod
    async def send_message(self, to_node_id: str | None, body: str, channel: str | None, expect_ack: bool) -> str | None:
        raise NotImplementedError

    async def send_advert(self, flood: bool = False) -> dict:
        raise NotImplementedError

    async def drain_pending_messages(self) -> None:
        return None

    async def get_device_info(self) -> dict:
        return {}

    async def get_gateway_telemetry(self) -> dict:
        return {}

    async def get_device_settings(self) -> list[dict]:
        return []

    async def request_node_status(self, node_id: str) -> dict:
        raise NotImplementedError

    async def request_node_telemetry(self, node_id: str) -> dict:
        raise NotImplementedError

    async def login_node(self, node_id: str, password: str) -> dict:
        raise NotImplementedError

    async def send_node_command(self, node_id: str, command: str) -> str | None:
        raise NotImplementedError

    async def remove_contact(self, node_id: str) -> dict:
        raise NotImplementedError

    async def update_device_settings(self, values: dict) -> None:
        raise NotImplementedError

    async def is_reachable(self) -> bool:
        return True
