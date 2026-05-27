from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any, TYPE_CHECKING

from sqlalchemy import select

from app.core.event_bus import AppEvent
from app.db.models import Message
from app.db.session import async_session

if TYPE_CHECKING:
    from app.meshcore.manager import MeshCoreManager


class AckTracker:
    def __init__(self, manager: MeshCoreManager) -> None:
        self.manager = manager

    async def expire_pending_ack_after_timeout(self, message_id) -> None:
        await asyncio.sleep(120)
        async with async_session() as session:
            message = await session.get(Message, message_id)
            if not message or message.status != "pending_ack":
                return
            message.status = "sent"
            message.delivery_state = "ack_timeout"
            raw_payload = dict(message.raw_payload or {})
            raw_payload["ack_timeout_seconds"] = 120
            message.raw_payload = raw_payload
            await session.commit()
            await session.refresh(message)

        await self.manager.event_bus.publish(
            AppEvent(
                type="message.delivery_updated",
                source="app",
                payload={
                    "id": str(message.id),
                    "status": message.status,
                    "delivery_state": message.delivery_state,
                    "raw_payload": message.raw_payload,
                },
            )
        )

    async def expire_stale_pending_acks(self) -> None:
        cutoff = datetime.now(UTC) - timedelta(seconds=120)
        async with async_session() as session:
            result = await session.execute(
                select(Message).where(
                    Message.direction == "outbound",
                    Message.status == "pending_ack",
                    Message.sent_at < cutoff,
                )
            )
            messages = result.scalars().all()
            for message in messages:
                message.status = "sent"
                message.delivery_state = "ack_timeout"
                raw_payload = dict(message.raw_payload or {})
                raw_payload.setdefault("ack_timeout_seconds", 120)
                message.raw_payload = raw_payload
            await session.commit()

    async def mark_recent_outbound_ack(self, ack_payload: dict[str, Any]) -> None:
        ack_id = self.ack_identifier(ack_payload)
        if not ack_id:
            await self._publish_unmatched_ack("ACK payload did not contain a packet identifier", None, ack_payload)
            return
        cutoff = datetime.now(UTC) - timedelta(minutes=10)
        async with async_session() as session:
            result = await session.execute(
                select(Message)
                .where(
                    Message.direction == "outbound",
                    Message.status == "pending_ack",
                    Message.expected_ack.is_(True),
                    Message.sent_at >= cutoff,
                    Message.meshcore_message_id == ack_id,
                )
                .limit(1)
            )
            message = result.scalar_one_or_none()
            if not message:
                await self._publish_unmatched_ack("No pending outbound message matched ACK identifier", ack_id, ack_payload)
                return

            raw_payload = dict(message.raw_payload or {})
            raw_payload["ack_payload"] = ack_payload.get("payload") or ack_payload
            raw_payload["ack_id"] = ack_id
            message.status = "delivered"
            message.delivery_state = "acknowledged"
            message.delivered_at = datetime.now(UTC)
            message.raw_payload = raw_payload
            await session.commit()
            await session.refresh(message)

        await self.manager.event_bus.publish(
            AppEvent(
                type="message.delivery_updated",
                source="meshcore",
                payload={
                    "id": str(message.id),
                    "status": message.status,
                    "delivery_state": message.delivery_state,
                    "delivered_at": message.delivered_at.isoformat() if message.delivered_at else None,
                    "raw_payload": message.raw_payload,
                },
            )
        )

    def ack_identifier(self, ack_payload: dict[str, Any]) -> str | None:
        payload = ack_payload.get("payload") if isinstance(ack_payload, dict) else None
        data = payload if isinstance(payload, dict) else ack_payload
        if not isinstance(data, dict):
            return None
        for key in ("pkt_payload", "expected_ack", "ack", "ack_id", "message_id"):
            value = data.get(key)
            if isinstance(value, bytes):
                return value.hex().lower()
            if isinstance(value, str) and value:
                return value.lower()
        raw_payload = data.get("payload")
        if isinstance(raw_payload, str) and len(raw_payload) >= 8:
            return raw_payload[-8:].lower()
        return None

    async def _publish_unmatched_ack(self, reason: str, ack_id: str | None, raw_payload: dict[str, Any]) -> None:
        payload: dict[str, Any] = {"reason": reason, "raw_payload": raw_payload}
        if ack_id:
            payload["ack_id"] = ack_id
        await self.manager.event_bus.publish(
            AppEvent(type="message.ack_unmatched", source="meshcore", severity="warning", payload=payload)
        )
