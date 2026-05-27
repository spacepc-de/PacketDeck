from collections.abc import AsyncIterator
import asyncio
import json
from typing import Any

import httpx

from app.meshcore.events import MeshCoreEvent
from app.meshcore.transports import MeshCoreTransport


class BridgeMeshCoreTransport(MeshCoreTransport):
    def __init__(self, bridge_url: str) -> None:
        self.bridge_url = bridge_url.rstrip("/")
        self._client = httpx.AsyncClient(timeout=20)
        self._connected = False

    async def connect(self) -> None:
        response = await self._client.post(f"{self.bridge_url}/connect")
        response.raise_for_status()
        self._connected = True

    async def disconnect(self) -> None:
        try:
            await self._client.post(f"{self.bridge_url}/disconnect")
        finally:
            self._connected = False
            await self._client.aclose()

    async def events(self) -> AsyncIterator[MeshCoreEvent]:
        while self._connected:
            try:
                async with self._client.stream("GET", f"{self.bridge_url}/events", timeout=None) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if not self._connected:
                            return
                        if not line:
                            continue
                        data = json.loads(line)
                        if str(data.get("type") or "").startswith("bridge."):
                            continue
                        yield MeshCoreEvent(**data)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                yield MeshCoreEvent(
                    type="system.error",
                    source="bridge",
                    severity="error",
                    payload={"meshcore_event_type": "disconnected", "error": str(exc)},
                )
                return

    async def send_message(
        self,
        to_node_id: str | None,
        body: str,
        channel: str | None,
        expect_ack: bool,
    ) -> str | None:
        response = await self._client.post(
            f"{self.bridge_url}/send",
            json={
                "to_node_id": to_node_id,
                "body": body,
                "channel": channel,
                "expect_ack": expect_ack,
            },
        )
        response.raise_for_status()
        return response.json().get("meshcore_message_id")

    async def get_device_info(self) -> dict[str, Any]:
        response = await self._client.get(f"{self.bridge_url}/device-info")
        response.raise_for_status()
        return response.json()

    async def get_gateway_telemetry(self) -> dict[str, Any]:
        response = await self._client.get(f"{self.bridge_url}/telemetry")
        response.raise_for_status()
        return response.json()

    async def get_device_settings(self) -> list[dict[str, Any]]:
        response = await self._client.get(f"{self.bridge_url}/settings")
        response.raise_for_status()
        return response.json()

    async def request_node_status(self, node_id: str) -> dict[str, Any]:
        response = await self._client.post(
            f"{self.bridge_url}/nodes/status",
            json={"node_id": node_id},
            timeout=75,
        )
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text
            try:
                detail_json = exc.response.json()
                detail = str(detail_json.get("detail") or detail_json)
            except ValueError:
                pass
            raise RuntimeError(detail) from exc
        return response.json()

    async def update_device_settings(self, values: dict[str, Any]) -> None:
        response = await self._client.patch(f"{self.bridge_url}/settings", json={"values": values})
        response.raise_for_status()

    async def is_reachable(self) -> bool:
        try:
            response = await self._client.get(f"{self.bridge_url}/status")
            response.raise_for_status()
            return response.json().get("state") == "connected"
        except Exception:
            return False
