from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any, TYPE_CHECKING

from sqlalchemy import String, select

from app.core.event_bus import AppEvent
from app.db.models import Message, Node
from app.db.session import async_session

if TYPE_CHECKING:
    from app.meshcore.manager import MeshCoreManager


class RemoteAdminService:
    def __init__(self, manager: MeshCoreManager) -> None:
        self.manager = manager
        self._locks: dict[str, asyncio.Lock] = {}
        self._pending_commands: dict[str, dict[str, Any]] = {}
        self._login_cache: dict[str, dict[str, Any]] = {}

    def clear_connection_scoped_caches(self) -> None:
        self._login_cache.clear()
        self._pending_commands.clear()

    async def run_node_admin_command(self, node_id: str, password: str, command: str) -> dict[str, Any]:
        lock = self._locks.setdefault(node_id, asyncio.Lock())
        async with lock:
            login = await self._ensure_node_admin_login_locked(node_id, password)
            result = await self._send_node_command_locked(node_id, command)
            return {**result, "login": login}

    async def send_node_command(self, node_id: str, command: str) -> dict[str, Any]:
        lock = self._locks.setdefault(node_id, asyncio.Lock())
        async with lock:
            return await self._send_node_command_locked(node_id, command)

    async def ensure_node_admin_login(self, node_id: str, password: str) -> dict[str, Any]:
        lock = self._locks.setdefault(node_id, asyncio.Lock())
        async with lock:
            return await self._ensure_node_admin_login_locked(node_id, password)

    async def _ensure_node_admin_login_locked(self, node_id: str, password: str) -> dict[str, Any]:
        now = datetime.now(UTC)
        cached = self._login_cache.get(node_id)
        if cached:
            expires_at = cached.get("expires_at")
            if isinstance(expires_at, datetime) and now < expires_at:
                return {
                    "is_admin": cached.get("is_admin"),
                    "pubkey_prefix": cached.get("pubkey_prefix"),
                    "cached": True,
                }
        payload = await asyncio.wait_for(self.manager.login_node(node_id, password), timeout=35)
        self._login_cache[node_id] = {
            "is_admin": bool(payload.get("is_admin")),
            "pubkey_prefix": payload.get("pubkey_prefix"),
            "expires_at": now + timedelta(minutes=15),
        }
        return {**payload, "cached": False}

    async def _send_node_command_locked(self, node_id: str, command: str) -> dict[str, Any]:
        manager = self.manager
        if not manager.transport or manager.state.state != "connected":
            raise RuntimeError("MeshCore device is not connected")
        destination = await manager._node_destination(node_id)
        command_message = await self._persist_admin_command(node_id, destination, command, "queued")
        sent_after = datetime.now(UTC)
        pending = {
            "node_id": node_id,
            "destination": destination,
            "command": command,
            "sent_after": sent_after.isoformat(),
            "message_db_id": str(command_message.id),
        }
        self._pending_commands[node_id] = pending
        await manager.event_bus.publish(AppEvent(type="message.admin_command_pending", source="meshcore", payload=pending))
        try:
            message_id = await manager.transport.send_node_command(destination, command)
            clean_message_id = None if message_id and set(str(message_id)) == {"0"} else message_id
            await self._update_admin_command(command_message.id, "sent", meshcore_message_id=clean_message_id)
            response = await self._wait_for_node_command_response(
                node_id,
                sent_after,
                command_message_id=str(command_message.id),
            )
            await self._update_admin_command(
                command_message.id,
                "response_received" if response else "sent",
                delivery_state="response_received" if response else "response_timeout",
                response=response,
            )
            return {
                "status": "response_received" if response else "sent",
                "meshcore_message_id": clean_message_id,
                "message_db_id": str(command_message.id),
                "command_response": response,
            }
        except Exception:
            await self._update_admin_command(command_message.id, "failed")
            raise
        finally:
            self._pending_commands.pop(node_id, None)

    async def _wait_for_node_command_response(
        self,
        node_id: str,
        sent_after: datetime,
        timeout_seconds: float = 45,
        command_message_id: str | None = None,
    ) -> dict[str, Any] | None:
        deadline = asyncio.get_running_loop().time() + timeout_seconds
        while asyncio.get_running_loop().time() < deadline:
            try:
                await self.manager.drain_pending_messages()
            except Exception:
                pass
            async with async_session() as session:
                result = await session.execute(
                    select(Message)
                    .where(
                        Message.direction == "inbound",
                        Message.from_node_id.cast(String) == node_id,
                        Message.message_type == "command_response",
                        Message.received_at >= sent_after,
                    )
                    .order_by(Message.received_at.asc())
                    .limit(10)
                )
                message = None
                for candidate in result.scalars().all():
                    if not self.manager._is_remote_command_response(candidate.raw_payload or {}):
                        continue
                    message = candidate
                    break
                if message:
                    if command_message_id:
                        raw_payload = dict(message.raw_payload or {})
                        raw_payload["admin_command_message_id"] = command_message_id
                        message.raw_payload = raw_payload
                        await session.commit()
                    return {
                        "id": str(message.id),
                        "body": message.body,
                        "received_at": message.received_at.isoformat() if message.received_at else None,
                        "raw_payload": message.raw_payload,
                    }
            await asyncio.sleep(2)
        return None

    async def _persist_admin_command(self, node_id: str, destination: str, command: str, status: str) -> Message:
        async with async_session() as session:
            result = await session.execute(select(Node).where(Node.id.cast(String) == node_id))
            node = result.scalar_one_or_none()
            message = Message(
                direction="outbound",
                message_type="admin_command",
                to_node_id=node.id if node else None,
                body=command,
                status=status,
                expected_ack=False,
                sent_at=datetime.now(UTC),
                raw_payload={
                    "source": "remote_admin",
                    "to_node_id": node_id,
                    "destination": destination,
                    "command": command,
                },
            )
            session.add(message)
            await session.commit()
            await session.refresh(message)
            return message

    async def _update_admin_command(
        self,
        message_id: Any,
        status: str,
        meshcore_message_id: str | None = None,
        delivery_state: str | None = None,
        response: dict[str, Any] | None = None,
    ) -> None:
        async with async_session() as session:
            message = await session.get(Message, message_id)
            if not message:
                return
            message.status = status
            if meshcore_message_id is not None:
                message.meshcore_message_id = meshcore_message_id
            if delivery_state is not None:
                message.delivery_state = delivery_state
            raw_payload = dict(message.raw_payload or {})
            if response:
                raw_payload["response_message_id"] = response.get("id")
                raw_payload["response_body"] = response.get("body")
                raw_payload["response_received_at"] = response.get("received_at")
                message.delivered_at = datetime.now(UTC)
            message.raw_payload = raw_payload
            await session.commit()
