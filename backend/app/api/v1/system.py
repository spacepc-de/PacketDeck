from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.event_bus import AppEvent
from app.core.event_bus import event_bus
from app.core.security import require_api_token
from app.db.session import get_db_session
from app.services.system_settings_service import RetentionSettings, apply_retention, get_retention_settings, update_retention_settings

router = APIRouter(dependencies=[Depends(require_api_token)])


@router.get("/events")
async def get_system_events(
    window_seconds: int = Query(default=300, ge=5, le=86400),
    limit: int = Query(default=200, ge=1, le=1000),
    source: str | None = Query(default=None),
    event_type: str | None = Query(default=None),
):
    return [
        {
            "id": event.id,
            "type": event.type,
            "source": event.source,
            "severity": event.severity,
            "payload": event.payload,
            "created_at": event.created_at.isoformat(),
        }
        for event in event_bus.list_events(
            window_seconds=window_seconds,
            limit=limit,
            source=source,
            event_type=event_type,
        )
    ]


@router.get("/settings")
async def get_system_settings(session: AsyncSession = Depends(get_db_session)):
    retention = await get_retention_settings(session)
    return {"retention": retention.model_dump()}


@router.patch("/settings")
async def patch_system_settings(payload: dict[str, RetentionSettings], session: AsyncSession = Depends(get_db_session)):
    retention = await update_retention_settings(session, payload["retention"].model_dump())
    cleanup = await apply_retention(session, retention)
    await event_bus.publish(
        AppEvent(
            type="system.settings_updated",
            source="app",
            payload={"retention": retention.model_dump(), "cleanup": cleanup},
        )
    )
    return {"retention": retention.model_dump(), "cleanup": cleanup}


@router.post("/retention/apply")
async def apply_system_retention(session: AsyncSession = Depends(get_db_session)):
    return await apply_retention(session)
