from datetime import UTC, datetime, timedelta
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import GatewayTelemetry, Node, NodeTelemetry, SystemSetting


class RetentionSettings(BaseModel):
    telemetry_retention_days: int = Field(default=30, ge=1, le=3650)
    node_retention_days: int = Field(default=90, ge=1, le=3650)
    telemetry_poll_interval_seconds: int = Field(default=30, ge=5, le=3600)
    favorite_node_telemetry_enabled: bool = True
    favorite_node_telemetry_interval_seconds: int = Field(default=300, ge=30, le=86400)


DEFAULT_RETENTION = RetentionSettings()


async def get_retention_settings(session: AsyncSession) -> RetentionSettings:
    db_setting = await session.get(SystemSetting, "retention")
    if not db_setting:
        db_setting = SystemSetting(key="retention", value=DEFAULT_RETENTION.model_dump())
        session.add(db_setting)
        await session.commit()
        await session.refresh(db_setting)
    return RetentionSettings(**(db_setting.value or {}))


async def update_retention_settings(session: AsyncSession, values: dict[str, Any]) -> RetentionSettings:
    settings = RetentionSettings(**values)
    db_setting = await session.get(SystemSetting, "retention")
    if not db_setting:
        db_setting = SystemSetting(key="retention", value=settings.model_dump())
        session.add(db_setting)
    else:
        db_setting.value = settings.model_dump()
    await session.commit()
    return settings


async def apply_retention(session: AsyncSession, settings: RetentionSettings | None = None) -> dict[str, int]:
    settings = settings or await get_retention_settings(session)
    now = datetime.now(UTC)
    telemetry_cutoff = now - timedelta(days=settings.telemetry_retention_days)
    node_cutoff = now - timedelta(days=settings.node_retention_days)

    gateway_result = await session.execute(
        delete(GatewayTelemetry).where(GatewayTelemetry.recorded_at < telemetry_cutoff)
    )
    node_telemetry_result = await session.execute(
        delete(NodeTelemetry).where(NodeTelemetry.recorded_at < telemetry_cutoff)
    )
    nodes_result = await session.execute(
        delete(Node).where(
            or_(
                Node.last_heard_at < node_cutoff,
                (Node.last_heard_at.is_(None) & (Node.updated_at < node_cutoff)),
            )
        )
    )
    await session.commit()
    return {
        "gateway_telemetry_deleted": gateway_result.rowcount or 0,
        "node_telemetry_deleted": node_telemetry_result.rowcount or 0,
        "nodes_deleted": nodes_result.rowcount or 0,
    }
