import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import require_api_token
from app.db.models import Message, Node, NodeAdminCredential, NodeEvent
from app.db.session import get_db_session

router = APIRouter(dependencies=[Depends(require_api_token)])


ADMIN_ROLE_MARKERS = ("router", "repeater", "room", "server")
DESTRUCTIVE_COMMAND_PREFIXES = (
    "reboot",
    "clkreboot",
    "start ota",
    "erase",
    "factory-reset",
    "password ",
    "set prv.key",
)
DUPLICATE_PREFIX_LENGTH = 12

REMOTE_UNSUPPORTED_COMMANDS = (
    "get acl",
    "get prv.key",
    "region list",
    "stats-core",
    "stats-radio",
    "stats-packets",
    "log",
    "erase",
)


class NodeFavoritePatch(BaseModel):
    is_favorite: bool


class RemoteAdminCommandIn(BaseModel):
    command: str = Field(min_length=1, max_length=180)
    confirm_destructive: bool = False


class NodeAdminCredentialIn(BaseModel):
    admin_password: str = Field(min_length=1, max_length=128)


class NodeAdminCredentialOut(BaseModel):
    has_admin_password: bool
    updated_at: str | None = None


def _node_destination(node: Node) -> str | None:
    return node.public_key or node.meshcore_id


def _node_prefix(node: Node) -> str | None:
    destination = _node_destination(node)
    if not destination:
        return None
    normalized = destination.lower()
    return normalized[:DUPLICATE_PREFIX_LENGTH] if len(normalized) >= DUPLICATE_PREFIX_LENGTH else None


def _duplicate_prefix_map(nodes: list[Node]) -> dict[str, list[Node]]:
    by_prefix: dict[str, list[Node]] = {}
    for node in nodes:
        prefix = _node_prefix(node)
        if prefix:
            by_prefix.setdefault(prefix, []).append(node)
    return {prefix: items for prefix, items in by_prefix.items() if len(items) > 1}


def _is_suspicious_stale_contact(node: Node) -> bool:
    destination = _node_destination(node) or ""
    raw_contact = (node.raw_info or {}).get("contact") if isinstance(node.raw_info, dict) else {}
    name = (node.display_name or node.short_name or raw_contact.get("adv_name") if isinstance(raw_contact, dict) else "") or ""
    contact_type = raw_contact.get("type") if isinstance(raw_contact, dict) else None
    return (
        destination.lower().endswith("0000")
        or contact_type == 0
        or name.upper() == destination[:6].upper()
    )


def _node_out(node: Node, duplicate_prefixes: dict[str, list[Node]] | None = None) -> dict:
    prefix = _node_prefix(node)
    duplicates = (duplicate_prefixes or {}).get(prefix or "", [])
    duplicate_nodes = [
        {
            "id": str(item.id),
            "display_name": item.display_name,
            "public_key": item.public_key,
            "meshcore_id": item.meshcore_id,
        }
        for item in duplicates
        if item.id != node.id
    ]
    warning = None
    if duplicate_nodes:
        warning = "Duplicate MeshCore public-key prefix. Private messages may fail until stale contacts are removed."
    elif _is_suspicious_stale_contact(node):
        warning = "This contact looks stale or incomplete."
    return {
        "id": str(node.id),
        "meshcore_id": node.meshcore_id,
        "public_key": node.public_key,
        "display_name": node.display_name,
        "short_name": node.short_name,
        "long_name": node.long_name,
        "is_favorite": node.is_favorite,
        "role": node.role,
        "status": node.status,
        "battery_percentage": node.battery_percentage,
        "battery_voltage_v": node.battery_voltage_v,
        "latitude": node.latitude,
        "longitude": node.longitude,
        "altitude": node.altitude,
        "last_heard_at": node.last_heard_at,
        "raw_info": node.raw_info,
        "duplicate_public_key_prefix": prefix if duplicate_nodes else None,
        "duplicate_nodes": duplicate_nodes,
        "suspect_stale_contact": _is_suspicious_stale_contact(node),
        "warning": warning,
    }


def _node_admin_supported(node: Node) -> bool:
    role = (node.role or "").lower()
    raw_role = str(
        (node.raw_info or {}).get("role") or (node.raw_info or {}).get("type") or ""
    ).lower()
    name = " ".join(
        str(value or "").lower()
        for value in (node.display_name, node.short_name, node.long_name, node.meshcore_id)
    )
    haystack = f"{role} {raw_role} {name}"
    return any(marker in haystack for marker in ADMIN_ROLE_MARKERS)


def _normalized_command(command: str) -> str:
    return " ".join(command.strip().split())


def _is_destructive_command(command: str) -> bool:
    lowered = command.lower()
    return any(
        lowered == prefix.strip() or lowered.startswith(prefix)
        for prefix in DESTRUCTIVE_COMMAND_PREFIXES
    )


def _is_remote_unsupported_command(command: str) -> bool:
    lowered = command.lower()
    return any(
        lowered == item or lowered.startswith(f"{item} ")
        for item in REMOTE_UNSUPPORTED_COMMANDS
    )


def _admin_capabilities(node: Node) -> dict:
    supported = _node_admin_supported(node)
    reason = None
    if not supported:
        reason = (
            "Remote administration is only offered for nodes that look like routers, "
            "repeaters, or room servers."
        )
    return {
        "supported": supported,
        "reason": reason,
        "transport": "meshcore_cli_message",
        "response_hint": (
            "Replies arrive as normal MeshCore messages and appear in Messages or node history."
        ),
        "presets": [
            {"label": "Version", "command": "ver", "destructive": False},
            {"label": "Board", "command": "board", "destructive": False},
            {"label": "Role", "command": "get role", "destructive": False},
            {"label": "Radio", "command": "get radio", "destructive": False},
            {"label": "TX Power", "command": "get tx", "destructive": False},
            {"label": "Repeat", "command": "get repeat", "destructive": False},
            {"label": "Neighbors", "command": "neighbors", "destructive": False},
            {"label": "Clock", "command": "clock", "destructive": False},
            {"label": "Sync Clock", "command": "clock sync", "destructive": False},
            {"label": "Room Read Only", "command": "get allow.read.only", "destructive": False},
            {"label": "Reboot", "command": "reboot", "destructive": True},
        ],
    }


async def _get_node_or_404(node_id: uuid.UUID, session: AsyncSession) -> Node:
    node = await session.get(Node, node_id)
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")
    return node


async def _get_admin_credential(
    node_id: uuid.UUID,
    session: AsyncSession,
) -> NodeAdminCredential | None:
    result = await session.execute(
        select(NodeAdminCredential).where(NodeAdminCredential.node_id == node_id)
    )
    return result.scalar_one_or_none()


def _credential_out(credential: NodeAdminCredential | None) -> NodeAdminCredentialOut:
    updated_at = None
    if credential and credential.updated_at:
        updated_at = credential.updated_at.isoformat()
    return NodeAdminCredentialOut(
        has_admin_password=credential is not None,
        updated_at=updated_at,
    )


@router.get("")
async def list_nodes(session: AsyncSession = Depends(get_db_session)):
    result = await session.execute(
        select(Node).order_by(Node.is_favorite.desc(), Node.last_heard_at.desc().nullslast())
    )
    nodes = list(result.scalars().all())
    duplicate_prefixes = _duplicate_prefix_map(nodes)
    return [_node_out(node, duplicate_prefixes) for node in nodes]


@router.post("/favorites/telemetry/refresh", status_code=202)
async def refresh_favorite_node_telemetry(request: Request):
    return await request.app.state.meshcore_manager.refresh_favorite_node_telemetry()


@router.post("/refresh")
async def refresh_nodes(request: Request):
    await request.app.state.meshcore_manager.refresh_gateway_telemetry()
    return {"status": "completed"}


@router.get("/{node_id}")
async def get_node(node_id: uuid.UUID, session: AsyncSession = Depends(get_db_session)):
    node = await _get_node_or_404(node_id, session)
    result = await session.execute(select(Node))
    duplicate_prefixes = _duplicate_prefix_map(list(result.scalars().all()))
    return _node_out(node, duplicate_prefixes)


@router.delete("/{node_id}/contact")
async def remove_node_contact(
    node_id: uuid.UUID,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
):
    node = await _get_node_or_404(node_id, session)
    destination = _node_destination(node)
    if not destination:
        raise HTTPException(status_code=400, detail="Node has no MeshCore public key")
    try:
        remove_result = await request.app.state.meshcore_manager.remove_contact(destination)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    await session.delete(node)
    await session.commit()
    return {"status": "removed", "device_result": remove_result}


@router.post("/{node_id}/telemetry/refresh", status_code=202)
async def refresh_node_telemetry(
    node_id: uuid.UUID,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
):
    node = await _get_node_or_404(node_id, session)
    credential = await _get_admin_credential(node_id, session)
    if credential is None and _node_admin_supported(node):
        raise HTTPException(
            status_code=409,
            detail="Save the node admin password before refreshing telemetry from this repeater.",
        )
    login_payload = None
    try:
        if credential is not None:
            login_payload = await request.app.state.meshcore_manager.login_node(str(node_id), credential.admin_password)
        result = await request.app.state.meshcore_manager.refresh_node_metrics(str(node_id))
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {
        "status": "updated",
        "status_payload": result.get("status"),
        "telemetry": result.get("telemetry"),
        "errors": result.get("errors", {}),
        "admin_login": {
            "used": credential is not None,
            "is_admin": bool((login_payload or {}).get("is_admin")),
            "pubkey_prefix": (login_payload or {}).get("pubkey_prefix"),
        },
    }


@router.patch("/{node_id}/favorite")
async def update_node_favorite(
    node_id: uuid.UUID,
    payload: NodeFavoritePatch,
    session: AsyncSession = Depends(get_db_session),
):
    node = await _get_node_or_404(node_id, session)
    node.is_favorite = payload.is_favorite
    await session.commit()
    await session.refresh(node)
    return node


@router.get("/{node_id}/admin/capabilities")
async def get_node_admin_capabilities(
    node_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
):
    node = await _get_node_or_404(node_id, session)
    return _admin_capabilities(node)


@router.get("/{node_id}/admin/credential", response_model=NodeAdminCredentialOut)
async def get_node_admin_credential(
    node_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
):
    await _get_node_or_404(node_id, session)
    credential = await _get_admin_credential(node_id, session)
    return _credential_out(credential)


@router.put("/{node_id}/admin/credential", response_model=NodeAdminCredentialOut)
async def save_node_admin_credential(
    node_id: uuid.UUID,
    payload: NodeAdminCredentialIn,
    session: AsyncSession = Depends(get_db_session),
):
    await _get_node_or_404(node_id, session)
    credential = await _get_admin_credential(node_id, session)
    if credential:
        credential.admin_password = payload.admin_password
    else:
        credential = NodeAdminCredential(
            node_id=node_id,
            admin_password=payload.admin_password,
        )
        session.add(credential)
    await session.commit()
    await session.refresh(credential)
    return _credential_out(credential)


@router.delete("/{node_id}/admin/credential", response_model=NodeAdminCredentialOut)
async def delete_node_admin_credential(
    node_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
):
    await _get_node_or_404(node_id, session)
    credential = await _get_admin_credential(node_id, session)
    if credential:
        await session.delete(credential)
        await session.commit()
    return _credential_out(None)


@router.post("/{node_id}/admin/commands", status_code=202)
async def send_node_admin_command(
    node_id: uuid.UUID,
    payload: RemoteAdminCommandIn,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
):
    node = await _get_node_or_404(node_id, session)
    if not _node_admin_supported(node):
        raise HTTPException(
            status_code=400,
            detail=(
                "Remote administration is only available for router, repeater, "
                "or room server nodes"
            ),
        )

    command = _normalized_command(payload.command)
    if _is_remote_unsupported_command(command):
        raise HTTPException(
            status_code=400,
            detail=(
                "This MeshCore CLI command is not suitable "
                "for remote execution"
            ),
        )
    if _is_destructive_command(command) and not payload.confirm_destructive:
        raise HTTPException(
            status_code=409,
            detail="This command can change or reboot the remote node and requires confirmation",
        )

    destination = node.public_key or node.meshcore_id
    if not destination:
        raise HTTPException(status_code=400, detail="Node has no MeshCore destination identifier")

    credential = await _get_admin_credential(node_id, session)
    if credential is None:
        raise HTTPException(status_code=400, detail="Admin password is required for remote administration")

    manager = request.app.state.meshcore_manager
    try:
        result = await manager.run_node_admin_command(str(node_id), credential.admin_password, command)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "status": result.get("status", "sent"),
        "meshcore_message_id": result.get("meshcore_message_id"),
        "message_db_id": result.get("message_db_id"),
        "command": command,
        "command_response": result.get("command_response"),
        "admin_password_configured": True,
        "login": {
            "is_admin": bool((result.get("login") or {}).get("is_admin")),
            "pubkey_prefix": (result.get("login") or {}).get("pubkey_prefix"),
        },
    }



@router.post("/{node_id}/status/request")
async def request_node_status(
    node_id: uuid.UUID,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
):
    await _get_node_or_404(node_id, session)
    credential = await _get_admin_credential(node_id, session)
    try:
        if credential is not None:
            await request.app.state.meshcore_manager.login_node(str(node_id), credential.admin_password)
        status = await request.app.state.meshcore_manager.request_node_status(str(node_id))
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "completed", "payload": status}


@router.get("/{node_id}/events")
async def get_node_events(node_id: uuid.UUID, session: AsyncSession = Depends(get_db_session)):
    result = await session.execute(
        select(NodeEvent).where(NodeEvent.node_id == node_id).order_by(NodeEvent.created_at.desc())
    )
    return result.scalars().all()


@router.get("/{node_id}/messages")
async def get_node_messages(node_id: uuid.UUID, session: AsyncSession = Depends(get_db_session)):
    result = await session.execute(
        select(Message)
        .where((Message.from_node_id == node_id) | (Message.to_node_id == node_id))
        .order_by(Message.received_at.desc().nullslast(), Message.sent_at.desc().nullslast())
    )
    return result.scalars().all()
