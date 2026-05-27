from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any, TYPE_CHECKING

from app.core.event_bus import AppEvent
from app.db.models import Message
from app.db.session import async_session
from app.meshcore.models import MessageSendRequest

if TYPE_CHECKING:
    from app.meshcore.manager import MeshCoreManager


class MessageService:
    def __init__(self, manager: MeshCoreManager) -> None:
        self.manager = manager

    async def send_message(self, request: MessageSendRequest) -> dict[str, str | None]:
        manager = self.manager
        if len(request.body) > manager.settings.meshcore_message_max_chars:
            raise ValueError(f"Message is too long. Maximum is {manager.settings.meshcore_message_max_chars} characters.")
        if request.channel in (None, "") and request.to_node_id:
            manager._ensure_direct_destination_available(request.to_node_id)
        db_message = await manager._persist_outgoing_message(request, None, "queued")
        try:
            if not manager.transport or manager.state.state != "connected":
                raise RuntimeError("MeshCore device is not connected")
            message_id = await manager.transport.send_message(
                request.to_node_id,
                request.body,
                request.channel,
                request.expect_ack,
            )
            status = "pending_ack" if request.expect_ack else "sent"
            delivery_state = "pending_ack" if request.expect_ack else None
            db_message = await manager._update_outgoing_message(
                db_message.id,
                message_id,
                status,
                delivery_state=delivery_state,
            )
            if request.expect_ack:
                asyncio.create_task(manager.ack_tracker.expire_pending_ack_after_timeout(db_message.id))
        except Exception:
            await manager._update_outgoing_message(db_message.id, None, "failed")
            raise
        await manager.event_bus.publish(
            AppEvent(
                type="message.sent",
                source="app",
                payload={
                    "id": str(db_message.id),
                    "to_node_id": str(db_message.to_node_id) if db_message.to_node_id else None,
                    "raw_to_node_id": request.to_node_id,
                    "body": request.body,
                    "channel": request.channel,
                    "meshcore_message_id": message_id,
                    "status": db_message.status,
                    "delivery_state": db_message.delivery_state,
                },
            )
        )
        return {"meshcore_message_id": message_id, "status": db_message.status, "message_db_id": str(db_message.id)}

    async def persist_incoming_message(self, event_payload: dict[str, Any]) -> None:
        manager = self.manager
        payload = event_payload.get("payload") or {}
        meshcore_type = event_payload.get("meshcore_event_type")
        if not isinstance(payload, dict):
            return

        body = manager._message_body(payload)
        is_command_response = manager._is_remote_command_response(payload)
        if not body:
            await manager.event_bus.publish(
                AppEvent(
                    type="message.unparsed",
                    source="meshcore",
                    severity="warning",
                    payload={"meshcore_event_type": meshcore_type, "raw_payload": payload},
                )
            )
            return

        async with async_session() as session:
            from_node = None
            pubkey_prefix = manager._message_pubkey_prefix(payload)
            if pubkey_prefix:
                from_node = await manager._get_or_create_node(session, pubkey_prefix)
                manager._update_node_route_info(from_node, payload, source="message_path")
            existing_message = await manager._find_existing_incoming_message(session, payload, body, meshcore_type)
            if existing_message:
                return

            message = Message(
                direction="inbound",
                message_type="command_response" if is_command_response else "text",
                from_node_id=from_node.id if from_node else None,
                channel=str(payload.get("channel_idx")) if meshcore_type in {"channel_message", "channel_msg"} else None,
                body=body,
                status="received",
                received_at=datetime.now(UTC),
                raw_payload=payload,
            )
            session.add(message)
            await session.commit()
            await session.refresh(message)

        app_payload = {
            "id": str(message.id),
            "from_node_id": str(message.from_node_id) if message.from_node_id else None,
            "channel": message.channel,
            "body": message.body,
            "message_type": message.message_type,
            "raw_payload": payload,
        }
        await manager.event_bus.publish(
            AppEvent(
                type="message.command_response_received" if is_command_response else "message.received",
                source="meshcore",
                payload=app_payload,
            )
        )
        if not is_command_response:
            await manager._run_message_automations({**app_payload, "from_meshcore_id": payload.get("pubkey_prefix")})
