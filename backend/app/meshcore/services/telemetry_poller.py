from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
import random
from typing import Any, TYPE_CHECKING

from sqlalchemy import select

from app.core.event_bus import AppEvent
from app.db.models import Node, NodeAdminCredential
from app.db.session import async_session
from app.services.system_settings_service import get_retention_settings

if TYPE_CHECKING:
    from app.meshcore.manager import MeshCoreManager


class TelemetryPoller:
    def __init__(self, manager: MeshCoreManager) -> None:
        self.manager = manager
        self._favorite_node_last_polled_at: dict[str, datetime] = {}
        self._favorite_node_backoff_until: dict[str, datetime] = {}
        self._favorite_node_failures: dict[str, int] = {}

    async def poll_gateway_telemetry(self) -> None:
        manager = self.manager
        while manager.state.state == "connected":
            try:
                async with async_session() as session:
                    retention = await get_retention_settings(session)
                await asyncio.sleep(retention.telemetry_poll_interval_seconds)
                if manager.state.state == "connected":
                    await manager.refresh_gateway_telemetry()
                    await manager._maybe_apply_retention()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                await manager.event_bus.publish(
                    AppEvent(
                        type="system.error",
                        source="app",
                        severity="error",
                        payload={"message": "Gateway telemetry polling failed", "error": str(exc)},
                    )
                )
                await asyncio.sleep(30)

    async def poll_favorite_node_telemetry(self) -> None:
        manager = self.manager
        while manager.state.state == "connected":
            try:
                async with async_session() as session:
                    retention = await get_retention_settings(session)
                interval = retention.favorite_node_telemetry_interval_seconds
                jitter = random.uniform(0, min(30, max(3, interval * 0.15)))
                await asyncio.sleep(interval + jitter)
                if manager.state.state != "connected" or not retention.favorite_node_telemetry_enabled:
                    continue
                result = await self.refresh_favorite_node_telemetry(
                    force=False,
                    round_timeout_seconds=max(15, min(60, interval * 0.5)),
                )
                await manager.event_bus.publish(
                    AppEvent(type="telemetry.favorite_nodes_refreshed", source="app", payload=result)
                )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                await manager.event_bus.publish(
                    AppEvent(
                        type="system.error",
                        source="app",
                        severity="warning",
                        payload={"message": "Favorite node telemetry polling failed", "error": str(exc)},
                    )
                )
                await asyncio.sleep(30)

    async def refresh_favorite_node_telemetry(
        self,
        force: bool = True,
        round_timeout_seconds: float | None = None,
    ) -> dict[str, Any]:
        manager = self.manager
        if not manager.transport or manager.state.state != "connected":
            return {"status": "disconnected", "updated": 0, "failed": 0, "skipped": 0, "nodes": []}
        async with async_session() as session:
            retention = await get_retention_settings(session)
            result = await session.execute(
                select(Node)
                .where(Node.is_favorite.is_(True))
                .order_by(Node.display_name.asc().nullslast(), Node.updated_at.desc())
            )
            nodes = list(result.scalars().all())
            credential_result = await session.execute(select(NodeAdminCredential))
            credentials = {str(item.node_id): item.admin_password for item in credential_result.scalars().all()}

        outcomes: list[dict[str, Any]] = []
        interval = retention.favorite_node_telemetry_interval_seconds
        min_node_interval = max(30, int(interval * 0.8))
        started_at = datetime.now(UTC)
        deadline = asyncio.get_running_loop().time() + round_timeout_seconds if round_timeout_seconds is not None else None
        for node in nodes:
            now = datetime.now(UTC)
            node_id = str(node.id)
            label = node.display_name or node.long_name or node.short_name or node.meshcore_id
            if deadline is not None and asyncio.get_running_loop().time() >= deadline:
                outcomes.append({"node_id": node_id, "label": label, "status": "skipped", "reason": "favorite telemetry poll time budget exhausted"})
                continue
            if not force:
                backoff_until = self._favorite_node_backoff_until.get(node_id)
                if backoff_until and now < backoff_until:
                    outcomes.append({"node_id": node_id, "label": label, "status": "skipped", "reason": f"backoff until {backoff_until.isoformat()}"})
                    continue
                last_polled_at = self._favorite_node_last_polled_at.get(node_id)
                if last_polled_at and now - last_polled_at < timedelta(seconds=min_node_interval):
                    outcomes.append({"node_id": node_id, "label": label, "status": "skipped", "reason": "minimum per-node interval not reached"})
                    continue
            try:
                password = credentials.get(node_id)
                login_payload = None
                if password:
                    login_payload = await asyncio.wait_for(
                        manager.remote_admin.ensure_node_admin_login(node_id, password),
                        timeout=self._remaining_timeout(deadline, default=20),
                    )
                metrics = await asyncio.wait_for(
                    manager.refresh_node_metrics(node_id),
                    timeout=self._remaining_timeout(deadline, default=25),
                )
                self._favorite_node_last_polled_at[node_id] = datetime.now(UTC)
                self._favorite_node_failures.pop(node_id, None)
                self._favorite_node_backoff_until.pop(node_id, None)
                outcomes.append(
                    {
                        "node_id": node_id,
                        "label": label,
                        "status": "updated",
                        "admin_login_used": bool(password),
                        "is_admin": bool((login_payload or {}).get("is_admin")),
                        "status_payload": metrics.get("status"),
                        "telemetry": metrics.get("telemetry"),
                        "errors": metrics.get("errors"),
                    }
                )
            except Exception as exc:
                failures = self._favorite_node_failures.get(node_id, 0) + 1
                self._favorite_node_failures[node_id] = failures
                backoff_seconds = min(900, 30 * (2 ** min(failures - 1, 5)))
                backoff_seconds += random.uniform(0, min(30, backoff_seconds * 0.2))
                self._favorite_node_backoff_until[node_id] = datetime.now(UTC) + timedelta(seconds=backoff_seconds)
                outcomes.append({"node_id": node_id, "label": label, "status": "failed", "error": str(exc)})
        return {
            "status": "completed",
            "updated": sum(1 for item in outcomes if item["status"] == "updated"),
            "failed": sum(1 for item in outcomes if item["status"] == "failed"),
            "skipped": sum(1 for item in outcomes if item["status"] == "skipped"),
            "elapsed_seconds": (datetime.now(UTC) - started_at).total_seconds(),
            "nodes": outcomes,
        }

    def _remaining_timeout(self, deadline: float | None, default: float) -> float:
        if deadline is None:
            return default
        remaining = deadline - asyncio.get_running_loop().time()
        return max(1, min(default, remaining))
