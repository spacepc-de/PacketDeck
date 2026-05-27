from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import String, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.event_bus import event_bus
from app.core.security import require_api_token
from app.db.models import Message, Node
from app.db.session import get_db_session
from app.meshcore.models import MessageSendRequest

router = APIRouter(dependencies=[Depends(require_api_token)])

DUPLICATE_PREFIX_LENGTH = 12


def _destination_prefix(destination: str | None) -> str | None:
    if not destination:
        return None
    normalized = destination.lower()
    return normalized[:DUPLICATE_PREFIX_LENGTH] if len(normalized) >= DUPLICATE_PREFIX_LENGTH else None


def _node_destination(node: Node) -> str | None:
    return node.public_key or node.meshcore_id


def _duplicate_prefixes(nodes: list[Node]) -> dict[str, list[Node]]:
    by_prefix: dict[str, list[Node]] = {}
    for node in nodes:
        prefix = _destination_prefix(_node_destination(node))
        if prefix:
            by_prefix.setdefault(prefix, []).append(node)
    return {prefix: items for prefix, items in by_prefix.items() if len(items) > 1}


def _duplicate_warning(prefix: str, nodes: list[Node]) -> dict:
    return {
        "duplicate_public_key_prefix": prefix,
        "warning": "Duplicate MeshCore public-key prefix. Remove stale contacts before sending private messages.",
        "duplicate_nodes": [
            {
                "id": str(node.id),
                "label": node.display_name or node.long_name or node.short_name or _node_destination(node),
                "public_key": node.public_key,
                "meshcore_id": node.meshcore_id,
            }
            for node in nodes
        ],
    }


@router.get("")
async def list_messages(session: AsyncSession = Depends(get_db_session)):
    result = await session.execute(
        select(Message)
        .where(Message.message_type == "text")
        .order_by(func.coalesce(Message.received_at, Message.sent_at).desc().nullslast())
        .limit(200)
    )
    return result.scalars().all()


@router.post("/sync")
async def sync_messages(request: Request):
    return await request.app.state.meshcore_manager.sync_pending_messages()


@router.get("/debug")
async def get_message_debug_events(
    window_seconds: int = Query(default=300, ge=5, le=86400),
    limit: int = Query(default=100, ge=1, le=500),
):
    interesting = {
        "messages_waiting",
        "no_more_messages",
        "contact_message",
        "channel_message",
        "command_error",
        "auto_message_fetching_started",
        "auto_message_fetching_failed",
        "message_sync_failed",
        "message_sync_timeout",
        "message_sync_result",
    }
    output = []
    for event in event_bus.list_events(window_seconds=window_seconds, limit=limit * 4):
        payload = event.payload if isinstance(event.payload, dict) else {}
        meshcore_type = payload.get("meshcore_event_type")
        if meshcore_type in interesting or event.type in {
            "message.received",
            "message.command_response_received",
            "message.unparsed",
        }:
            output.append(
                {
                    "id": event.id,
                    "type": event.type,
                    "source": event.source,
                    "severity": event.severity,
                    "meshcore_event_type": meshcore_type,
                    "payload": event.payload,
                    "created_at": event.created_at.isoformat(),
                }
            )
        if len(output) >= limit:
            break
    return output


@router.get("/limits")
async def get_message_limits(request: Request):
    return {"max_body_chars": request.app.state.meshcore_manager.settings.meshcore_message_max_chars}


@router.get("/targets")
async def list_message_targets(request: Request, include_empty: bool = False, session: AsyncSession = Depends(get_db_session)):
    messages_result = await session.execute(
        select(Message)
        .where(Message.message_type == "text")
        .order_by(func.coalesce(Message.received_at, Message.sent_at).desc().nullslast())
        .limit(500)
    )
    recent_messages = messages_result.scalars().all()

    node_result = await session.execute(
        select(Node).order_by(Node.is_favorite.desc(), Node.last_heard_at.desc().nullslast())
    )
    nodes = list(node_result.scalars().all())
    duplicate_prefixes = _duplicate_prefixes(nodes)

    latest_by_node: dict[str, Message] = {}
    latest_by_channel: dict[str, Message] = {}
    raw_node_ids: set[str] = set()

    for message in recent_messages:
        node_id = message.from_node_id or message.to_node_id
        if node_id and str(node_id) not in latest_by_node:
            latest_by_node[str(node_id)] = message
        if message.channel is not None and str(message.channel) not in latest_by_channel:
            latest_by_channel[str(message.channel)] = message
        raw_to_node_id = (message.raw_payload or {}).get("to_node_id")
        raw_from_node_id = (
            (message.raw_payload or {}).get("pubkey_prefix")
            or (message.raw_payload or {}).get("pubkey_pre")
            or (message.raw_payload or {}).get("public_key")
            or (message.raw_payload or {}).get("adv_key")
        )
        for raw_node_id in (raw_to_node_id, raw_from_node_id):
            if isinstance(raw_node_id, str) and raw_node_id:
                raw_node_ids.add(raw_node_id)

    active_destinations = _active_gateway_destinations(request)
    targets = []
    known_node_destinations: set[str] = set()
    for node in nodes:
        destination = node.public_key or node.meshcore_id
        if destination:
            normalized_destination = destination.lower()
            if (
                active_destinations
                and normalized_destination not in active_destinations
                and normalized_destination[:12] not in active_destinations
            ):
                continue
            known_node_destinations.add(normalized_destination)
            known_node_destinations.add(normalized_destination[:12])
        latest_message = latest_by_node.get(str(node.id))
        if not include_empty and latest_message is None:
            continue
        latest_at = (latest_message.received_at or latest_message.sent_at) if latest_message else None
        prefix = _destination_prefix(destination)
        warning = _duplicate_warning(prefix, duplicate_prefixes[prefix]) if prefix in duplicate_prefixes else {}
        targets.append(
            {
                "id": f"node:{node.id}",
                "type": "node",
                "label": node.display_name or node.long_name or node.short_name or destination or "Unknown node",
                "detail": f"Node · {node.status}" if node.status else "Node",
                "toNodeId": destination,
                "channel": None,
                "isFavorite": node.is_favorite,
                "lastMessage": latest_message.body if latest_message else None,
                "lastAt": latest_at.isoformat() if latest_at else None,
                **warning,
            }
        )

    for raw_node_id in sorted(raw_node_ids):
        normalized_raw_node_id = raw_node_id.lower()
        if normalized_raw_node_id in known_node_destinations:
            continue
        if (
            active_destinations
            and normalized_raw_node_id not in active_destinations
            and normalized_raw_node_id[:12] not in active_destinations
        ):
            continue
        targets.append(
            {
                "id": f"node:raw:{raw_node_id}",
                "type": "node",
                "label": raw_node_id[:12].upper(),
                "detail": "Node",
                "toNodeId": raw_node_id,
                "channel": None,
                "isFavorite": False,
                "lastMessage": None,
                "lastAt": None,
            }
        )

    for channel, latest_message in latest_by_channel.items():
        latest_at = latest_message.received_at or latest_message.sent_at
        targets.append(
            {
                "id": f"channel:{channel}",
                "type": "channel",
                "label": f"Channel {channel}",
                "detail": f"Channel {channel}",
                "toNodeId": None,
                "channel": channel,
                "isFavorite": False,
                "lastMessage": latest_message.body,
                "lastAt": latest_at.isoformat() if latest_at else None,
            }
        )

    return targets


@router.get("/conversations")
async def list_conversations(session: AsyncSession = Depends(get_db_session)):
    result = await session.execute(
        select(Message)
        .where(Message.message_type == "text")
        .order_by(func.coalesce(Message.received_at, Message.sent_at).desc().nullslast())
        .limit(500)
    )
    conversations: dict[str, dict] = {}
    for message in result.scalars().all():
        key = message.channel if message.channel is not None else str(message.from_node_id or message.to_node_id or "unknown")
        if key not in conversations:
            conversations[key] = {
                "id": key,
                "channel": message.channel,
                "last_message": message.body,
                "last_at": (message.received_at or message.sent_at).isoformat() if (message.received_at or message.sent_at) else None,
            }
    return list(conversations.values())


@router.get("/conversations/{node_id}")
async def get_conversation(node_id: str, session: AsyncSession = Depends(get_db_session)):
    filters = [Message.channel == node_id]
    try:
        import uuid

        node_uuid = uuid.UUID(node_id)
        filters.extend([Message.from_node_id == node_uuid, Message.to_node_id == node_uuid])
    except ValueError:
        pass
    result = await session.execute(
        select(Message)
        .where(Message.message_type == "text", or_(*filters))
        .order_by(func.coalesce(Message.received_at, Message.sent_at).asc().nullslast())
        .limit(500)
    )
    return {"node_id": node_id, "messages": result.scalars().all()}


@router.post("/send", status_code=202)
async def send_message(request: Request, payload: MessageSendRequest, session: AsyncSession = Depends(get_db_session)):
    if payload.channel in (None, "") and payload.to_node_id:
        await _raise_on_duplicate_direct_destination(payload.to_node_id, session)
    try:
        send_result = await request.app.state.meshcore_manager.send_message(payload)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if send_result.get("message_db_id"):
        import uuid

        db_message = await session.get(Message, uuid.UUID(str(send_result["message_db_id"])))
        if db_message:
            return db_message
    to_node = None
    if payload.to_node_id:
        result = await session.execute(
            select(Node).where(
                or_(
                    Node.id.cast(String) == payload.to_node_id,
                    Node.meshcore_id == payload.to_node_id,
                    Node.public_key == payload.to_node_id,
                )
            )
        )
        to_node = result.scalar_one_or_none()

    db_message = Message(
        direction="outbound",
        message_type="text",
        to_node_id=to_node.id if to_node else None,
        body=payload.body,
        channel=payload.channel,
        status=send_result["status"] or "queued",
        expected_ack=payload.expect_ack,
        meshcore_message_id=send_result["meshcore_message_id"],
        sent_at=datetime.now(UTC),
        raw_payload={"to_node_id": payload.to_node_id, "channel": payload.channel},
    )
    session.add(db_message)
    await session.commit()
    await session.refresh(db_message)
    return db_message


async def _raise_on_duplicate_direct_destination(destination: str, session: AsyncSession) -> None:
    result = await session.execute(select(Node))
    nodes = list(result.scalars().all())
    resolved_destination = destination
    for node in nodes:
        if str(node.id) == destination or node.meshcore_id == destination or node.public_key == destination:
            resolved_destination = _node_destination(node) or destination
            break
    prefix = _destination_prefix(resolved_destination)
    if not prefix:
        return
    duplicates = _duplicate_prefixes(nodes).get(prefix, [])
    if duplicates:
        labels = [
            node.display_name or node.long_name or node.short_name or _node_destination(node) or str(node.id)
            for node in duplicates
        ]
        raise HTTPException(
            status_code=409,
            detail=(
                "Private message blocked because multiple MeshCore contacts share "
                f"prefix {prefix}: {', '.join(labels)}. Remove stale duplicate contacts first."
            ),
        )


def _active_gateway_destinations(request: Request) -> set[str]:
    manager = getattr(request.app.state, "meshcore_manager", None)
    latest = getattr(manager, "latest_gateway_telemetry", None) or {}
    raw = latest.get("raw_payload") if isinstance(latest, dict) else {}
    contacts = raw.get("contacts") if isinstance(raw, dict) and isinstance(raw.get("contacts"), dict) else {}
    destinations: set[str] = set()
    for key, contact in contacts.items():
        for value in (key, (contact or {}).get("public_key") if isinstance(contact, dict) else None):
            if isinstance(value, str) and value:
                normalized = value.lower()
                destinations.add(normalized)
                destinations.add(normalized[:12])
    return destinations
