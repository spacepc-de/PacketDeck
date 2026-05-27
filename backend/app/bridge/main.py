from collections.abc import AsyncIterator
import asyncio
from datetime import UTC, datetime
import json
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.core.config import get_settings
from app.meshcore.events import MeshCoreEvent
from app.meshcore.serial_transport import SerialMeshCoreTransport


class SendRequest(BaseModel):
    to_node_id: str | None = None
    body: str
    channel: str | None = None
    expect_ack: bool = True


class SettingsPatch(BaseModel):
    values: dict[str, Any]


class NodeStatusRequest(BaseModel):
    node_id: str


class BridgeService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.transport: SerialMeshCoreTransport | None = None
        self.state = "disconnected"
        self.device_identifier: str | None = None
        self.last_connected_at: datetime | None = None
        self.last_disconnected_at: datetime | None = None
        self.last_error: str | None = None
        self._event_task: asyncio.Task | None = None
        self._connect_lock = asyncio.Lock()
        self._subscribers: set[asyncio.Queue[dict[str, Any]]] = set()

    async def start(self) -> None:
        if self.settings.meshcore_auto_reconnect:
            asyncio.create_task(self.connect())

    async def stop(self) -> None:
        await self.disconnect()

    async def connect(self) -> dict[str, Any]:
        async with self._connect_lock:
            if self.transport and self.state == "connected":
                return self.status()
            await self.disconnect()
            self.state = "connecting"
            self.last_error = None
            try:
                transport = SerialMeshCoreTransport(
                    self.settings.meshcore_serial_port,
                    self.settings.meshcore_serial_baud,
                )
                await transport.connect()
                self.transport = transport
                self.state = "connected"
                self.device_identifier = transport.port
                self.last_connected_at = datetime.now(UTC)
                self._event_task = asyncio.create_task(self._forward_events())
                await self._publish(
                    {
                        "type": "bridge.status_changed",
                        "source": "bridge",
                        "severity": "info",
                        "payload": self.status(),
                    }
                )
            except Exception as exc:
                self.state = "error"
                self.last_error = str(exc)
                await self.disconnect(keep_error=True)
                raise HTTPException(status_code=503, detail=self.last_error)
            return self.status()

    async def disconnect(self, keep_error: bool = False) -> dict[str, Any]:
        if self._event_task:
            self._event_task.cancel()
            self._event_task = None
        if self.transport:
            await self.transport.disconnect()
            self.transport = None
        if not keep_error:
            self.last_error = None
        if self.state != "error":
            self.state = "disconnected"
        self.last_disconnected_at = datetime.now(UTC)
        return self.status()

    def status(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "connection_type": "serial",
            "device_identifier": self.device_identifier,
            "last_connected_at": self.last_connected_at.isoformat() if self.last_connected_at else None,
            "last_disconnected_at": self.last_disconnected_at.isoformat()
            if self.last_disconnected_at
            else None,
            "last_error": self.last_error,
        }

    async def send_message(self, request: SendRequest) -> dict[str, str | None]:
        if not self.transport or self.state != "connected":
            raise HTTPException(status_code=503, detail="Bridge serial transport is not connected")
        message_id = await self.transport.send_message(
            request.to_node_id,
            request.body,
            request.channel,
            request.expect_ack,
        )
        return {"meshcore_message_id": message_id}

    async def get_device_info(self) -> dict[str, Any]:
        if not self.transport or self.state != "connected":
            return {}
        return await self.transport.get_device_info()

    async def get_telemetry(self) -> dict[str, Any]:
        if not self.transport or self.state != "connected":
            raise HTTPException(status_code=503, detail="Bridge serial transport is not connected")
        return await self.transport.get_gateway_telemetry()

    async def get_settings(self) -> list[dict[str, Any]]:
        if not self.transport or self.state != "connected":
            return []
        return await self.transport.get_device_settings()

    async def request_node_status(self, node_id: str) -> dict[str, Any]:
        if not self.transport or self.state != "connected":
            raise HTTPException(status_code=503, detail="Bridge serial transport is not connected")
        try:
            return await self.transport.request_node_status(node_id)
        except RuntimeError as exc:
            raise HTTPException(status_code=408, detail=str(exc)) from exc

    async def update_settings(self, values: dict[str, Any]) -> None:
        if not self.transport or self.state != "connected":
            raise HTTPException(status_code=503, detail="Bridge serial transport is not connected")
        await self.transport.update_device_settings(values)

    async def subscribe(self) -> AsyncIterator[str]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=500)
        self._subscribers.add(queue)
        try:
            yield json.dumps({"type": "bridge.status_changed", "payload": self.status()}) + "\n"
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15)
                    yield json.dumps(event) + "\n"
                except TimeoutError:
                    yield json.dumps({"type": "bridge.ping", "payload": {}}) + "\n"
        finally:
            self._subscribers.discard(queue)

    async def _forward_events(self) -> None:
        assert self.transport is not None
        try:
            async for event in self.transport.events():
                data = event.model_dump(mode="json")
                await self._publish(data)
                meshcore_type = event.payload.get("meshcore_event_type")
                if meshcore_type == "disconnected":
                    self.state = "error"
                    self.last_error = "Serial event stream disconnected"
                    self.last_disconnected_at = datetime.now(UTC)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self.state = "error"
            self.last_error = str(exc)
            await self._publish(
                MeshCoreEvent(
                    type="system.error",
                    source="bridge",
                    severity="error",
                    payload={"meshcore_event_type": "disconnected", "error": str(exc)},
                ).model_dump(mode="json")
            )

    async def _publish(self, event: dict[str, Any]) -> None:
        for queue in list(self._subscribers):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                _ = queue.get_nowait()
                queue.put_nowait(event)


service = BridgeService()
app = FastAPI(title="PacketDeck MeshCore Bridge")


@app.on_event("startup")
async def startup() -> None:
    await service.start()


@app.on_event("shutdown")
async def shutdown() -> None:
    await service.stop()


@app.get("/status")
async def status():
    return service.status()


@app.post("/connect")
async def connect():
    return await service.connect()


@app.post("/disconnect")
async def disconnect():
    return await service.disconnect()


@app.get("/events")
async def events():
    return StreamingResponse(service.subscribe(), media_type="application/x-ndjson")


@app.post("/send")
async def send(request: SendRequest):
    return await service.send_message(request)


@app.get("/device-info")
async def device_info():
    return await service.get_device_info()


@app.get("/telemetry")
async def telemetry():
    return await service.get_telemetry()


@app.get("/settings")
async def settings():
    return await service.get_settings()


@app.post("/nodes/status")
async def node_status(request: NodeStatusRequest):
    return await service.request_node_status(request.node_id)


@app.patch("/settings")
async def update_settings(patch: SettingsPatch):
    await service.update_settings(patch.values)
    return {"status": "ok"}
