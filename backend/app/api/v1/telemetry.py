import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import require_api_token
from app.db.models import GatewayTelemetry, NodeTelemetry
from app.db.session import get_db_session

router = APIRouter(dependencies=[Depends(require_api_token)])


@router.get("/gateway/latest")
async def get_latest_gateway_telemetry(request: Request, session: AsyncSession = Depends(get_db_session)):
    live = request.app.state.meshcore_manager.latest_gateway_telemetry
    if live:
        return live
    result = await session.execute(select(GatewayTelemetry).order_by(GatewayTelemetry.recorded_at.desc()).limit(1))
    return result.scalar_one_or_none()


@router.get("/gateway/history")
async def get_gateway_telemetry_history(
    limit: int = Query(default=100, ge=1, le=1000),
    range: str | None = Query(default="24h"),
    from_: datetime | None = Query(default=None, alias="from"),
    until: datetime | None = Query(default=None),
    metric: str | None = Query(default=None),
    session: AsyncSession = Depends(get_db_session),
):
    query = select(GatewayTelemetry)
    start = from_ or _range_start(range)
    if start:
        query = query.where(GatewayTelemetry.recorded_at >= start)
    if until:
        query = query.where(GatewayTelemetry.recorded_at <= until)
    if metric and hasattr(GatewayTelemetry, metric):
        query = query.where(getattr(GatewayTelemetry, metric).is_not(None))
    result = await session.execute(query.order_by(GatewayTelemetry.recorded_at.desc()).limit(limit))
    return list(reversed(result.scalars().all()))


@router.get("/nodes/{node_id}/latest")
async def get_latest_node_telemetry(node_id: uuid.UUID, session: AsyncSession = Depends(get_db_session)):
    result = await session.execute(
        select(NodeTelemetry).where(NodeTelemetry.node_id == node_id).order_by(NodeTelemetry.recorded_at.desc()).limit(1)
    )
    return result.scalar_one_or_none()


@router.get("/nodes/{node_id}/history")
async def get_node_telemetry_history(
    node_id: uuid.UUID,
    limit: int = Query(default=100, ge=1, le=1000),
    range: str | None = Query(default="24h"),
    from_: datetime | None = Query(default=None, alias="from"),
    until: datetime | None = Query(default=None),
    session: AsyncSession = Depends(get_db_session),
):
    query = select(NodeTelemetry).where(NodeTelemetry.node_id == node_id)
    start = from_ or _range_start(range)
    if start:
        query = query.where(NodeTelemetry.recorded_at >= start)
    if until:
        query = query.where(NodeTelemetry.recorded_at <= until)
    result = await session.execute(query.order_by(NodeTelemetry.recorded_at.desc()).limit(limit))
    return list(reversed(result.scalars().all()))


def _range_start(value: str | None) -> datetime | None:
    if not value:
        return None
    amount = int(value[:-1]) if value[:-1].isdigit() else 0
    unit = value[-1]
    if amount <= 0:
        return None
    now = datetime.now(UTC)
    if unit == "h":
        return now - timedelta(hours=amount)
    if unit == "d":
        return now - timedelta(days=amount)
    if unit == "m":
        return now - timedelta(minutes=amount)
    return None
