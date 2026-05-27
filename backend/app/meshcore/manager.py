import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
import re
from typing import Any

from sqlalchemy import String, select

from app.core.config import Settings
from app.core.event_bus import AppEvent, EventBus
from app.db.models import GatewayTelemetry, Message, Node, NodeAdminCredential, NodeEvent, NodeTelemetry
from app.db.session import async_session
from app.meshcore.client import build_transport
from app.meshcore.models import ConnectionState, DeviceSetting, MessageSendRequest
from app.meshcore.wifi_transport import WifiTcpMeshCoreTransport
from app.meshcore.transports import MeshCoreTransport
from app.meshcore.services.ack_tracker import AckTracker
from app.meshcore.services.message_service import MessageService
from app.meshcore.services.remote_admin import RemoteAdminService
from app.meshcore.services.telemetry_poller import TelemetryPoller
from app.services.system_settings_service import apply_retention, get_retention_settings
from app.services.automation_service import process_automation_event
from app.services.telemetry_service import normalize_gateway_telemetry


class MeshCoreManager:
    def __init__(self, settings: Settings, event_bus: EventBus) -> None:
        self.settings = settings
        self.event_bus = event_bus
        self.transport: MeshCoreTransport | None = None
        self.state = ConnectionState(connection_type=settings.meshcore_connection_type)
        self.device_info: dict[str, Any] = {}
        self.latest_gateway_telemetry: dict[str, Any] | None = None
        self._event_task: asyncio.Task | None = None
        self._telemetry_task: asyncio.Task | None = None
        self._favorite_telemetry_task: asyncio.Task | None = None
        self._auto_reconnect_task: asyncio.Task | None = None
        self._disconnect_health_task: asyncio.Task | None = None
        self._connect_lock = asyncio.Lock()
        self._contact_persist_lock = asyncio.Lock()
        self.ack_tracker = AckTracker(self)
        self.message_service = MessageService(self)
        self.remote_admin = RemoteAdminService(self)
        self.telemetry_poller = TelemetryPoller(self)
        self._manual_disconnect = False
        self._last_retention_run: datetime | None = None
        self._last_transport_event_at: datetime | None = None
        self._active_device_identifier: str | None = f"{settings.meshcore_tcp_host}:{settings.meshcore_tcp_port}"

    async def start(self) -> None:
        asyncio.create_task(self.ack_tracker.expire_stale_pending_acks())
        if self.settings.meshcore_auto_reconnect and not self._auto_reconnect_task:
            self._auto_reconnect_task = asyncio.create_task(self._auto_reconnect_loop())
            asyncio.create_task(self.connect())

    async def shutdown(self) -> None:
        if self._auto_reconnect_task:
            self._auto_reconnect_task.cancel()
            self._auto_reconnect_task = None
        if self._disconnect_health_task:
            self._disconnect_health_task.cancel()
            self._disconnect_health_task = None
        await self.disconnect(manual=False)

    async def connect(self) -> ConnectionState:
        async with self._connect_lock:
            self._manual_disconnect = False
            if self.transport and self.state.state == "connected":
                await self._validate_connection()
                if self.state.state == "connected":
                    return self.state
            if self.transport:
                try:
                    await asyncio.wait_for(self.transport.disconnect(), timeout=2)
                except Exception:
                    pass
                self.transport = None
            await self._set_state("connecting")
            try:
                self.transport = await self._build_configured_transport()
                await self.transport.connect()
                self.device_info = getattr(self.transport, "_device_info", {}) or {}
                await self._set_state(
                    "connected",
                    device_identifier=self._connected_device_identifier(),
                    last_connected_at=datetime.now(UTC),
                    last_error=None,
                    reconnect_attempt_count=0,
                    api_library_version="meshcore",
                    firmware_version=self.device_info.get("ver"),
                )
                self._event_task = asyncio.create_task(self._forward_transport_events())
                self._telemetry_task = asyncio.create_task(self.telemetry_poller.poll_gateway_telemetry())
                self._favorite_telemetry_task = asyncio.create_task(self.telemetry_poller.poll_favorite_node_telemetry())
                asyncio.create_task(self._refresh_gateway_telemetry_once())
            except Exception as exc:
                if self.transport:
                    try:
                        await asyncio.wait_for(self.transport.disconnect(), timeout=2)
                    except Exception:
                        pass
                    self.transport = None
                await self._set_state("error", last_error=self._format_connection_error(exc))
        return self.state

    async def disconnect(self, manual: bool = True) -> ConnectionState:
        self._manual_disconnect = manual
        if self._event_task:
            self._event_task.cancel()
            self._event_task = None
        if self._telemetry_task:
            self._telemetry_task.cancel()
            self._telemetry_task = None
        if self._favorite_telemetry_task:
            self._favorite_telemetry_task.cancel()
            self._favorite_telemetry_task = None
        if self._disconnect_health_task:
            self._disconnect_health_task.cancel()
            self._disconnect_health_task = None
        if self.transport:
            await self.transport.disconnect()
            self.transport = None
        self._clear_connection_scoped_caches()
        await self._set_state("disconnected", last_disconnected_at=datetime.now(UTC))
        return self.state

    async def get_state(self) -> ConnectionState:
        if self.state.state == "connected":
            await self._validate_connection()
        return self.state

    async def send_message(self, request: MessageSendRequest) -> dict[str, str | None]:
        return await self.message_service.send_message(request)

    async def get_device_info(self) -> dict[str, str | None]:
        return {
            "name": self.device_info.get("name"),
            "firmware_version": self.state.firmware_version,
            "hardware_model": self.device_info.get("model"),
            "meshcore_library_version": self.state.api_library_version,
            "raw_info": self.device_info,
        }

    async def send_advert(self, flood: bool = False) -> dict[str, Any]:
        if not self.transport or self.state.state != "connected":
            raise RuntimeError("MeshCore device is not connected")
        result = await self.transport.send_advert(flood=flood)
        await self.event_bus.publish(
            AppEvent(
                type="meshcore.advert_sent",
                source="app",
                payload={"status": result.get("status", "sent"), "flood": flood},
            )
        )
        return result

    async def sync_pending_messages(self) -> dict[str, Any]:
        if not self.transport or self.state.state != "connected":
            return {"status": "disconnected", "events": []}
        try:
            result = await asyncio.wait_for(self.transport.drain_pending_messages(), timeout=12)
        except TimeoutError:
            await self.event_bus.publish(
                AppEvent(
                    type="system.error",
                    source="app",
                    severity="warning",
                    payload={"meshcore_event_type": "message_sync_timeout", "message": "MeshCore message sync timed out"},
                )
            )
            return {"status": "timeout", "events": []}
        if isinstance(result, dict):
            return result
        return {"status": "ok", "events": []}

    async def drain_pending_messages(self) -> None:
        await self.sync_pending_messages()

    async def refresh_gateway_telemetry(self) -> dict[str, Any] | None:
        if not self.transport or self.state.state != "connected":
            return self.latest_gateway_telemetry
        if not await self.transport.is_reachable():
            await self._mark_connection_lost("Connection to the MeshCore device was interrupted.")
            return self.latest_gateway_telemetry
        telemetry = await self.transport.get_gateway_telemetry()
        telemetry["recorded_at"] = datetime.now(UTC).isoformat()
        self.latest_gateway_telemetry = telemetry
        await self._persist_gateway_telemetry(telemetry, source="poll")
        await self.event_bus.publish(
            AppEvent(type="telemetry.gateway_updated", payload=telemetry)
        )
        return telemetry

    async def _refresh_gateway_telemetry_once(self) -> None:
        try:
            await self.refresh_gateway_telemetry()
        except Exception as exc:
            await self.event_bus.publish(
                AppEvent(
                    type="system.error",
                    source="app",
                    severity="error",
                    payload={"message": "Initial gateway telemetry refresh failed", "error": str(exc)},
                )
            )

    async def get_settings(self) -> list[DeviceSetting]:
        if not self.transport or self.state.state != "connected":
            return [
                DeviceSetting(key="connection_required", label="Device connection", category="System", editable=False, available=False),
            ]
        raw_settings = await self.transport.get_device_settings()
        return [DeviceSetting(**setting) for setting in raw_settings]

    async def update_settings(self, values: dict[str, Any]) -> list[DeviceSetting]:
        if not self.transport or self.state.state != "connected":
            raise RuntimeError("MeshCore device is not connected")
        await self.transport.update_device_settings(values)
        await self.event_bus.publish(AppEvent(type="device.settings_updated", payload={"keys": list(values.keys())}))
        return await self.get_settings()

    async def _node_destination(self, node_id: str) -> str:
        async with async_session() as session:
            node = await session.get(Node, node_id)
            if not node:
                raise RuntimeError("Node not found")
            destination = node.public_key or node.meshcore_id
        if not destination:
            raise RuntimeError("Node has no MeshCore destination identifier")
        return destination

    async def remove_contact(self, destination: str) -> dict[str, Any]:
        if not self.transport or self.state.state != "connected":
            raise RuntimeError("MeshCore device is not connected")
        return await self.transport.remove_contact(destination)

    async def refresh_node_telemetry(self, node_id: str) -> dict[str, Any]:
        if not self.transport or self.state.state != "connected":
            raise RuntimeError("MeshCore device is not connected")
        destination = await self._node_destination(node_id)
        telemetry = await self.transport.request_node_telemetry(destination)
        await self._persist_node_telemetry_response({"payload": telemetry, "attributes": {"pubkey_prefix": telemetry.get("pubkey_pre") or destination[:12]}})
        return telemetry

    async def refresh_node_metrics(self, node_id: str) -> dict[str, Any]:
        status: dict[str, Any] | None = None
        telemetry: dict[str, Any] | None = None
        errors: dict[str, str] = {}
        try:
            status = await self.request_node_status(node_id)
        except Exception as exc:
            errors["status"] = str(exc)
        try:
            telemetry = await self.refresh_node_telemetry(node_id)
        except Exception as exc:
            errors["telemetry"] = str(exc)
        if status is None and telemetry is None:
            raise RuntimeError("Node did not return status or telemetry")
        return {"status": status, "telemetry": telemetry, "errors": errors}

    async def request_node_status(self, node_id: str) -> dict[str, Any]:
        if not self.transport or self.state.state != "connected":
            raise RuntimeError("MeshCore device is not connected")
        destination = await self._node_destination(node_id)

        status = await self.transport.request_node_status(destination)
        if isinstance(status, dict) and status.get("lpp") is not None:
            await self._persist_node_telemetry_response({"payload": status, "attributes": {"pubkey_prefix": status.get("pubkey_pre")}})
        else:
            await self._persist_node_status_response(status)
        return status

    async def login_node(self, node_id: str, password: str) -> dict[str, Any]:
        if not self.transport or self.state.state != "connected":
            raise RuntimeError("MeshCore device is not connected")
        destination = await self._node_destination(node_id)
        return await self.transport.login_node(destination, password)

    async def send_node_command(self, node_id: str, command: str) -> dict[str, Any]:
        return await self.remote_admin.send_node_command(node_id, command)

    async def run_node_admin_command(self, node_id: str, password: str, command: str) -> dict[str, Any]:
        return await self.remote_admin.run_node_admin_command(node_id, password, command)

    async def _forward_transport_events(self) -> None:
        assert self.transport is not None
        async for event in self.transport.events():
            meshcore_type = event.payload.get("meshcore_event_type")
            if meshcore_type == "disconnected":
                disconnected_at = datetime.now(UTC)
                await self.event_bus.publish(
                    AppEvent(
                        type="meshcore.disconnected",
                        payload=event.payload,
                        source=event.source,
                        severity=event.severity,
                    )
                )
                self._schedule_disconnect_health_check(disconnected_at)
                continue
            self._last_transport_event_at = datetime.now(UTC)
            if self._is_ack_event(event.payload):
                await self.ack_tracker.mark_recent_outbound_ack(event.payload)
            if self._is_incoming_text_event(meshcore_type, event.payload):
                await self.message_service.persist_incoming_message(event.payload)
            if meshcore_type == "contacts":
                await self._persist_contact_event(event.payload.get("payload"))
            elif meshcore_type == "next_contact":
                payload = event.payload.get("payload")
                if isinstance(payload, dict):
                    public_key = payload.get("public_key")
                    await self._persist_contact_event({public_key: payload} if public_key else None)
            elif meshcore_type == "telemetry_response":
                await self._persist_node_telemetry_response(event.payload)
            elif meshcore_type == "status_response":
                await self._persist_node_status_response(event.payload.get("payload") or event.payload)
            await self.event_bus.publish(
                AppEvent(
                    type=f"meshcore.{meshcore_type}" if meshcore_type else event.type,
                    payload=event.payload,
                    source=event.source,
                    severity=event.severity,
                )
            )

    async def _persist_contact_event(self, contacts: Any) -> None:
        async with self._contact_persist_lock:
            async with async_session() as session:
                events = await self._persist_contact_nodes(session, contacts)
                await session.commit()
        for event in events:
            await self.event_bus.publish(event)

    async def _persist_node_status_response(self, status: dict[str, Any]) -> None:
        if not isinstance(status, dict):
            return
        pubkey_prefix = str(status.get("pubkey_pre") or status.get("pubkey_prefix") or "")
        if not pubkey_prefix or self._is_self_pubkey_prefix(pubkey_prefix):
            return
        battery_mv = self._decimal_or_none(status.get("bat") or status.get("battery_mv"))
        battery_voltage_v = battery_mv / Decimal("1000") if battery_mv is not None else None
        async with async_session() as session:
            node = await self._get_or_create_node(session, pubkey_prefix)
            node.status = "online"
            node.last_heard_at = datetime.now(UTC)
            if battery_voltage_v is not None:
                node.battery_voltage_v = battery_voltage_v
            raw_info = dict(node.raw_info or {})
            raw_info["status"] = {"payload": status, "updated_at": datetime.now(UTC).isoformat()}
            node.raw_info = raw_info
            telemetry = NodeTelemetry(
                node_id=node.id,
                recorded_at=datetime.now(UTC),
                battery_voltage_v=battery_voltage_v,
                rssi=self._decimal_or_none(status.get("last_rssi")),
                snr=self._decimal_or_none(status.get("last_snr")),
                noise_floor=self._decimal_or_none(status.get("noise_floor")),
                uptime_seconds=self._int_or_none(status.get("uptime") or status.get("uptime_secs") or status.get("uptime_seconds")),
                packets_received=self._int_or_none(status.get("nb_recv") or status.get("packets_received") or status.get("recv")),
                packets_sent=self._int_or_none(status.get("nb_sent") or status.get("packets_sent") or status.get("sent")),
                packet_receive_errors=self._int_or_none(status.get("recv_errors") or status.get("packet_receive_errors")),
                tx_queue_len=self._int_or_none(status.get("tx_queue_len") or status.get("queue_len")),
                airtime=self._int_or_none(status.get("airtime")),
                rx_airtime=self._int_or_none(status.get("rx_airtime")),
                sent_flood=self._int_or_none(status.get("sent_flood")),
                sent_direct=self._int_or_none(status.get("sent_direct")),
                recv_flood=self._int_or_none(status.get("recv_flood")),
                recv_direct=self._int_or_none(status.get("recv_direct")),
                direct_dups=self._int_or_none(status.get("direct_dups")),
                flood_dups=self._int_or_none(status.get("flood_dups")),
                full_events=self._int_or_none(status.get("full_evts") or status.get("full_events")),
                raw_payload={"source": "status_response", "payload": status},
            )
            session.add(telemetry)
            await session.commit()
            await session.refresh(node)
            await session.refresh(telemetry)

        await self.event_bus.publish(
            AppEvent(
                type="telemetry.node_updated",
                source="meshcore",
                payload={
                    "node_id": str(node.id),
                    "telemetry_id": str(telemetry.id),
                    "battery_voltage_v": self._json_number(battery_voltage_v),
                    "rssi": self._json_number(telemetry.rssi),
                    "snr": self._json_number(telemetry.snr),
                    "noise_floor": self._json_number(telemetry.noise_floor),
                    "uptime_seconds": telemetry.uptime_seconds,
                    "packets_received": telemetry.packets_received,
                    "packets_sent": telemetry.packets_sent,
                    "packet_receive_errors": telemetry.packet_receive_errors,
                    "raw_payload": telemetry.raw_payload,
                },
            )
        )

    async def _persist_node_telemetry_response(self, event_payload: dict[str, Any]) -> None:
        payload = event_payload.get("payload") or {}
        attributes = event_payload.get("attributes") or {}
        if not isinstance(payload, dict) or not isinstance(attributes, dict):
            return

        pubkey_prefix = str(
            payload.get("pubkey_pre")
            or payload.get("pubkey_prefix")
            or attributes.get("pubkey_prefix")
            or ""
        )
        if not pubkey_prefix or self._is_self_pubkey_prefix(pubkey_prefix):
            return

        values = self._node_telemetry_values(payload)
        async with async_session() as session:
            node = await self._get_or_create_node(session, pubkey_prefix)
            node.status = "online"
            node.last_heard_at = datetime.now(UTC)
            if values["battery_percentage"] is not None:
                node.battery_percentage = values["battery_percentage"]
            if values["battery_voltage_v"] is not None:
                node.battery_voltage_v = values["battery_voltage_v"]
            if values["latitude"] is not None:
                node.latitude = values["latitude"]
            if values["longitude"] is not None:
                node.longitude = values["longitude"]
            if values["altitude"] is not None:
                node.altitude = values["altitude"]

            raw_info = dict(node.raw_info or {})
            raw_info["telemetry"] = {"payload": payload, "attributes": attributes, "updated_at": datetime.now(UTC).isoformat()}
            node.raw_info = raw_info

            telemetry = NodeTelemetry(
                node_id=node.id,
                recorded_at=datetime.now(UTC),
                latitude=values["latitude"],
                longitude=values["longitude"],
                altitude=values["altitude"],
                battery_percentage=values["battery_percentage"],
                battery_voltage_v=values["battery_voltage_v"],
                rssi=values["rssi"],
                snr=values["snr"],
                hops=values["hops"],
                raw_payload={"source": "telemetry_response", "payload": payload, "attributes": attributes},
            )
            session.add(telemetry)
            await session.commit()
            await session.refresh(node)
            await session.refresh(telemetry)

        await self.event_bus.publish(
            AppEvent(
                type="telemetry.node_updated",
                source="meshcore",
                payload={
                    "node_id": str(node.id),
                    "telemetry_id": str(telemetry.id),
                    "battery_percentage": self._json_number(values["battery_percentage"]),
                    "battery_voltage_v": self._json_number(values["battery_voltage_v"]),
                    "raw_payload": telemetry.raw_payload,
                },
            )
        )

    def _is_self_pubkey_prefix(self, pubkey_prefix: str) -> bool:
        raw = (self.latest_gateway_telemetry or {}).get("raw_payload") or {}
        self_public_key = str((raw.get("self_info") or {}).get("public_key") or "")
        self_prefix = str((raw.get("self_telemetry") or {}).get("pubkey_pre") or "")
        return bool(
            (self_public_key and self_public_key.startswith(pubkey_prefix))
            or (self_prefix and self_prefix.startswith(pubkey_prefix))
            or (pubkey_prefix and pubkey_prefix.startswith(self_prefix) and self_prefix)
        )

    def _current_contact_destinations(self) -> set[str]:
        raw = (self.latest_gateway_telemetry or {}).get("raw_payload") or {}
        contacts = raw.get("contacts") if isinstance(raw.get("contacts"), dict) else {}
        destinations: set[str] = set()
        for key, contact in contacts.items():
            for value in (key, (contact or {}).get("public_key") if isinstance(contact, dict) else None):
                if isinstance(value, str) and value:
                    normalized = value.lower()
                    destinations.add(normalized)
                    destinations.add(normalized[:12])
        return destinations

    def _ensure_direct_destination_available(self, to_node_id: str) -> None:
        normalized = to_node_id.lower()
        if self._is_self_pubkey_prefix(normalized[:12]):
            raise RuntimeError("Cannot send a direct MeshCore message to the connected gateway itself.")
        known_destinations = self._current_contact_destinations()
        if known_destinations and normalized not in known_destinations and normalized[:12] not in known_destinations:
            raise RuntimeError(
                "This node is not in the currently connected MeshCore gateway contact list. "
                "Wait until the Heltec discovers it, refresh nodes, or send to a channel instead."
            )

    def _node_telemetry_values(self, payload: dict[str, Any]) -> dict[str, Any]:
        lpp_values = payload.get("lpp") if isinstance(payload.get("lpp"), list) else []
        values = {
            "battery_percentage": self._decimal_or_none(payload.get("battery_percentage") or payload.get("battery")),
            "battery_voltage_v": self._decimal_or_none(payload.get("battery_voltage_v") or payload.get("battery_voltage")),
            "latitude": self._decimal_or_none(payload.get("latitude") or payload.get("lat")),
            "longitude": self._decimal_or_none(payload.get("longitude") or payload.get("lon") or payload.get("lng")),
            "altitude": self._decimal_or_none(payload.get("altitude") or payload.get("alt")),
            "rssi": self._decimal_or_none(payload.get("rssi")),
            "snr": self._decimal_or_none(payload.get("snr") or payload.get("SNR")),
            "hops": self._int_or_none(payload.get("hops") or payload.get("path_len")),
        }
        for item in lpp_values:
            if not isinstance(item, dict):
                continue
            item_type = str(item.get("type") or "").lower()
            item_value = item.get("value")
            channel = self._int_or_none(item.get("channel"))
            if item_type == "voltage" and values["battery_voltage_v"] is None:
                if channel in (None, 1):
                    values["battery_voltage_v"] = self._decimal_or_none(item_value)
            elif item_type in {"battery", "battery_percentage", "percentage", "percent"} and values["battery_percentage"] is None:
                values["battery_percentage"] = self._decimal_or_none(item_value)
            elif item_type in {"location", "gps"} and isinstance(item_value, dict):
                values["latitude"] = values["latitude"] or self._decimal_or_none(item_value.get("lat") or item_value.get("latitude"))
                values["longitude"] = values["longitude"] or self._decimal_or_none(item_value.get("lon") or item_value.get("lng") or item_value.get("longitude"))
                values["altitude"] = values["altitude"] or self._decimal_or_none(item_value.get("alt") or item_value.get("altitude"))
            elif item_type == "latitude" and values["latitude"] is None:
                values["latitude"] = self._decimal_or_none(item_value)
            elif item_type == "longitude" and values["longitude"] is None:
                values["longitude"] = self._decimal_or_none(item_value)
            elif item_type == "altitude" and values["altitude"] is None:
                values["altitude"] = self._decimal_or_none(item_value)
        return values

    def _decimal_or_none(self, value: Any) -> Decimal | None:
        if value in (None, ""):
            return None
        try:
            return Decimal(str(value))
        except (InvalidOperation, ValueError):
            return None

    def _int_or_none(self, value: Any) -> int | None:
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def _json_number(self, value: Any) -> float | int | None:
        if value is None:
            return None
        if isinstance(value, Decimal):
            return float(value)
        return value

    def _schedule_disconnect_health_check(self, disconnected_at: datetime) -> None:
        if self._disconnect_health_task and not self._disconnect_health_task.done():
            return
        self._disconnect_health_task = asyncio.create_task(
            self._delayed_disconnect_health_check(disconnected_at)
        )

    async def _delayed_disconnect_health_check(self, disconnected_at: datetime) -> None:
        try:
            await asyncio.sleep(12)
            if self.state.state != "connected" or self._manual_disconnect:
                return
            if self._last_transport_event_at and self._last_transport_event_at > disconnected_at:
                return
            await self._mark_connection_lost(
                "MeshCore WiFi TCP event stream disconnected. Reconnecting to restore message receive handling."
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            await self.event_bus.publish(
                AppEvent(
                    type="system.error",
                    source="app",
                    severity="error",
                    payload={"message": "MeshCore disconnect health check failed", "error": str(exc)},
                )
            )

    def _is_ack_event(self, event_payload: dict[str, Any]) -> bool:
        payload = event_payload.get("payload") or {}
        if not isinstance(payload, dict):
            return False
        return (
            str(event_payload.get("meshcore_event_type") or "") == "rx_log_data"
            and str(payload.get("payload_typename") or payload.get("type") or "").upper() == "ACK"
        )

    async def _set_state(self, state: str, **updates) -> None:
        data = self.state.model_dump()
        data.update(updates)
        data["state"] = state
        self.state = ConnectionState(**data)
        await self.event_bus.publish(AppEvent(type="connection.status_changed", payload=self.state.model_dump(mode="json"), source="app"))

    async def _validate_connection(self) -> None:
        if not self.transport:
            await self._set_state("disconnected", last_error="MeshCore transport is not available")
            return
        if not await self.transport.is_reachable():
            await self._mark_connection_lost("Connection to the MeshCore device was interrupted.")

    async def _mark_connection_lost(self, message: str) -> None:
        current_task = asyncio.current_task()
        if self._event_task and self._event_task is not current_task:
            self._event_task.cancel()
            self._event_task = None
        if self._telemetry_task and self._telemetry_task is not current_task:
            self._telemetry_task.cancel()
            self._telemetry_task = None
        if self._favorite_telemetry_task and self._favorite_telemetry_task is not current_task:
            self._favorite_telemetry_task.cancel()
            self._favorite_telemetry_task = None
        if self.transport:
            try:
                await asyncio.wait_for(self.transport.disconnect(), timeout=2)
            except Exception:
                pass
            self.transport = None
        self._clear_connection_scoped_caches()
        await self._set_state(
            "error",
            last_error=message,
            last_disconnected_at=datetime.now(UTC),
        )
        await self.event_bus.publish(
            AppEvent(
                type="system.error",
                source="app",
                severity="error",
                payload={"message": message},
            )
        )

    def _clear_connection_scoped_caches(self) -> None:
        self.remote_admin.clear_connection_scoped_caches()

    async def refresh_favorite_node_telemetry(
        self,
        force: bool = True,
        round_timeout_seconds: float | None = None,
    ) -> dict[str, Any]:
        return await self.telemetry_poller.refresh_favorite_node_telemetry(force, round_timeout_seconds)

    async def _auto_reconnect_loop(self) -> None:
        await asyncio.sleep(1)
        while True:
            try:
                await asyncio.sleep(5)
                if self._manual_disconnect or self.state.state in {"connected", "connecting", "reconnecting"}:
                    continue
                await self._set_state(
                    "reconnecting",
                    reconnect_attempt_count=self.state.reconnect_attempt_count + 1,
                )
                await self.connect()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                await self._set_state("error", last_error=self._format_connection_error(exc))

    def _format_connection_error(self, exc: Exception) -> str:
        return f"MeshCore WiFi TCP device is not reachable at {self.settings.meshcore_tcp_host}:{self.settings.meshcore_tcp_port}. Check WiFi and the companion port."

    def _connected_device_identifier(self) -> str | None:
        return f"{self.settings.meshcore_tcp_host}:{self.settings.meshcore_tcp_port}"

    async def _build_configured_transport(self) -> MeshCoreTransport:
        self._active_device_identifier = self._connected_device_identifier()
        await self._set_state(self.state.state, connection_type="tcp")
        return WifiTcpMeshCoreTransport(self.settings.meshcore_tcp_host, self.settings.meshcore_tcp_port)

    def _is_incoming_text_event(self, meshcore_type: Any, event_payload: dict[str, Any]) -> bool:
        return meshcore_type in {"contact_message", "channel_message", "contact_msg", "channel_msg"}

    async def _persist_gateway_telemetry(self, telemetry: dict[str, Any], source: str) -> None:
        normalized = normalize_gateway_telemetry(telemetry)
        normalized["source"] = source
        normalized["recorded_at"] = datetime.now(UTC)
        async with self._contact_persist_lock:
            async with async_session() as session:
                session.add(GatewayTelemetry(**normalized))
                node_events = await self._persist_contact_nodes(session, telemetry.get("raw_payload", {}).get("contacts"))
                await session.commit()
        for event in node_events:
            await self.event_bus.publish(event)

    async def _maybe_apply_retention(self) -> None:
        now = datetime.now(UTC)
        if self._last_retention_run and now - self._last_retention_run < timedelta(hours=1):
            return
        async with async_session() as session:
            result = await apply_retention(session)
        self._last_retention_run = now
        await self.event_bus.publish(AppEvent(type="system.retention_applied", source="app", payload=result))

    async def _find_existing_incoming_message(
        self,
        session,
        payload: dict[str, Any],
        body: str,
        meshcore_type: str | None,
    ) -> Message | None:
        sender_timestamp = payload.get("sender_timestamp")
        pubkey_prefix = payload.get("pubkey_prefix")
        if sender_timestamp is None or not pubkey_prefix:
            return None
        result = await session.execute(
            select(Message)
            .where(
                Message.direction == "inbound",
                Message.body == body,
            )
            .order_by(Message.received_at.desc().nullslast())
            .limit(50)
        )
        for message in result.scalars().all():
            raw_payload = message.raw_payload or {}
            if (
                str(raw_payload.get("sender_timestamp")) == str(sender_timestamp)
                and str(raw_payload.get("pubkey_prefix")) == str(pubkey_prefix)
                and str(raw_payload.get("type") or "") == str(payload.get("type") or "")
            ):
                return message
        return None

    def _message_body(self, payload: dict[str, Any]) -> str | None:
        for key in ("text", "body", "message", "msg", "content", "decoded_text"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip("\x00")
        decoded = self._decode_packet_text(payload.get("pkt_payload"))
        if decoded:
            return decoded
        data = payload.get("data") or payload.get("payload")
        if isinstance(data, str) and data.strip():
            return data.strip("\x00")
        if isinstance(data, bytes):
            text = data.decode("utf-8", errors="replace").strip().strip("\x00")
            return text or data.hex()
        return None

    def _decode_packet_text(self, value: Any) -> str | None:
        if not value:
            return None
        if isinstance(value, bytes):
            data = value
        elif isinstance(value, str):
            try:
                data = bytes.fromhex(value)
            except ValueError:
                return value.strip("\x00") or None
        else:
            return None
        candidates = []
        if len(data) > 5:
            candidates.append(data[5:])
        candidates.append(data)
        for candidate in candidates:
            text = candidate.decode("utf-8", errors="ignore").strip().strip("\x00")
            if text and any(char.isprintable() and not char.isspace() for char in text):
                return text
        return None

    def _message_pubkey_prefix(self, payload: dict[str, Any]) -> str | None:
        for key in ("pubkey_prefix", "pubkey_pre", "public_key", "adv_key"):
            value = payload.get(key)
            if isinstance(value, str) and value:
                return value[:12]
        return None

    def _is_remote_command_response(self, payload: dict[str, Any]) -> bool:
        try:
            return int(payload.get("txt_type")) == 1
        except (TypeError, ValueError):
            return False

    async def _persist_outgoing_message(
        self,
        request: MessageSendRequest,
        meshcore_message_id: str | None,
        status: str,
    ) -> Message:
        async with async_session() as session:
            to_node = None
            if request.to_node_id:
                result = await session.execute(
                    select(Node).where(
                        (Node.meshcore_id == request.to_node_id)
                        | (Node.public_key == request.to_node_id)
                        | (Node.id.cast(String) == request.to_node_id)
                    )
                )
                to_node = result.scalar_one_or_none()

            message = Message(
                direction="outbound",
                message_type="text",
                to_node_id=to_node.id if to_node else None,
                body=request.body,
                channel=request.channel,
                status=status,
                expected_ack=request.expect_ack,
                meshcore_message_id=meshcore_message_id,
                sent_at=datetime.now(UTC),
                raw_payload={
                    "to_node_id": request.to_node_id,
                    "channel": request.channel,
                    "source": "manager",
                },
            )
            session.add(message)
            await session.commit()
            await session.refresh(message)
            return message

    async def _update_outgoing_message(
        self,
        message_id,
        meshcore_message_id: str | None,
        status: str,
        delivery_state: str | None = None,
    ) -> Message:
        async with async_session() as session:
            message = await session.get(Message, message_id)
            if not message:
                raise RuntimeError("Queued message could not be found")
            message.status = status
            message.delivery_state = delivery_state
            if meshcore_message_id:
                message.meshcore_message_id = meshcore_message_id
            if status in {"sent", "pending_ack"} and not message.sent_at:
                message.sent_at = datetime.now(UTC)
            await session.commit()
            await session.refresh(message)
            return message

    async def _expire_pending_ack_after_timeout(self, message_id) -> None:
        await self.ack_tracker.expire_pending_ack_after_timeout(message_id)

    async def _expire_stale_pending_acks(self) -> None:
        await self.ack_tracker.expire_stale_pending_acks()

    async def _mark_recent_outbound_ack(self, ack_payload: dict[str, Any]) -> None:
        await self.ack_tracker.mark_recent_outbound_ack(ack_payload)

    def _ack_identifier(self, ack_payload: dict[str, Any]) -> str | None:
        return self.ack_tracker.ack_identifier(ack_payload)

    async def _run_message_automations(self, payload: dict[str, Any]) -> None:
        async with async_session() as session:
            runs = await process_automation_event(session, self.settings, "message.received", payload, self)
        for run in runs:
            await self.event_bus.publish(
                AppEvent(
                    type="automation.completed" if run.status == "completed" else "system.error",
                    source="app",
                    severity="info" if run.status == "completed" else "error",
                    payload={
                        "run_id": str(run.id),
                        "rule_id": str(run.rule_id) if run.rule_id else None,
                        "status": run.status,
                        "error_message": run.error_message,
                    },
                )
            )

    async def _persist_contact_nodes(self, session, contacts: Any) -> list[AppEvent]:
        events: list[AppEvent] = []
        if not isinstance(contacts, dict):
            return events
        for contact in contacts.values():
            if not isinstance(contact, dict):
                continue
            public_key = contact.get("public_key")
            if not self._valid_contact(contact):
                continue
            public_key = str(public_key)
            public_key_prefix = str(public_key)[:12]
            result = await session.execute(
                select(Node).where(
                    (Node.public_key == public_key)
                    | (Node.meshcore_id == public_key)
                    | (Node.meshcore_id == public_key_prefix)
                )
            )
            node = result.scalar_one_or_none()
            is_new = node is None
            if node is None:
                node = Node(
                    meshcore_id=public_key,
                    public_key=public_key,
                    first_seen_at=datetime.now(UTC),
                    created_at=datetime.now(UTC),
                )
                session.add(node)
                await session.flush()

            previous_status = node.status
            node.public_key = public_key
            node.meshcore_id = node.meshcore_id or public_key
            node.short_name = contact.get("adv_name") or node.short_name or public_key[:6].upper()
            node.display_name = contact.get("adv_name") or node.display_name or node.short_name
            node.role = self._contact_type_label(contact.get("type"))
            node.status = "online"
            node.last_heard_at = self._meshcore_timestamp(contact.get("last_advert")) or node.last_heard_at or datetime.now(UTC)
            node.latitude = contact.get("adv_lat") if contact.get("adv_lat") not in (None, 0, 0.0) else node.latitude
            node.longitude = contact.get("adv_lon") if contact.get("adv_lon") not in (None, 0, 0.0) else node.longitude
            self._update_node_route_info(node, contact, source="contacts")
            node.raw_info = {**(node.raw_info or {}), "contact": contact}

            hops = self._hop_count(contact)
            session.add(
                NodeTelemetry(
                    node_id=node.id,
                    recorded_at=datetime.now(UTC),
                    latitude=node.latitude,
                    longitude=node.longitude,
                    battery_percentage=node.battery_percentage,
                    battery_voltage_v=node.battery_voltage_v,
                    hops=hops,
                    raw_payload={
                        "source": "contacts",
                        "public_key": public_key,
                        "route": (node.raw_info or {}).get("route"),
                        "contact": contact,
                    },
                )
            )
            if is_new:
                session.add(NodeEvent(node_id=node.id, event_type="node.discovered", event_payload={"source": "contacts"}))
                events.append(
                    AppEvent(
                        type="node.discovered",
                        source="meshcore",
                        payload={
                            "node_id": str(node.id),
                            "display_name": node.display_name,
                            "public_key": public_key,
                            "role": node.role,
                            "hops": hops,
                            "raw_payload": contact,
                        },
                    )
                )
            elif previous_status != node.status:
                session.add(
                    NodeEvent(
                        node_id=node.id,
                        event_type="node.status_changed",
                        event_payload={"from": previous_status, "to": node.status, "source": "contacts"},
                    )
                )
                events.append(
                    AppEvent(
                        type="node.status_changed",
                        source="meshcore",
                        payload={
                            "node_id": str(node.id),
                            "display_name": node.display_name,
                            "from": previous_status,
                            "to": node.status,
                            "raw_payload": contact,
                        },
                    )
                )
            events.append(
                AppEvent(
                    type="meshcore.advertisement",
                    source="meshcore",
                    payload={
                        "node_id": str(node.id),
                        "display_name": node.display_name,
                        "public_key": public_key,
                        "role": node.role,
                        "last_advert": contact.get("last_advert"),
                        "hops": hops,
                        "route": (node.raw_info or {}).get("route"),
                        "raw_payload": contact,
                    },
                )
            )
        return events

    def _update_node_route_info(self, node: Node, payload: dict[str, Any], source: str) -> None:
        raw_info = dict(node.raw_info or {})
        route = self._route_info(payload)
        if route:
            raw_info["route"] = {**route, "source": source, "updated_at": datetime.now(UTC).isoformat()}
        node.raw_info = raw_info

    def _route_info(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        hops = self._hop_count(payload)
        path = payload.get("out_path") or payload.get("path")
        hash_mode = payload.get("out_path_hash_mode", payload.get("path_hash_mode"))
        route_hashes = self._split_route_hashes(path, hash_mode, hops)
        if hops is None and not route_hashes:
            return None
        return {
            "hops": hops,
            "path_hash_mode": hash_mode,
            "path": path,
            "path_hashes": route_hashes,
            "path_display": " -> ".join(route_hashes) if route_hashes else None,
        }

    def _hop_count(self, payload: dict[str, Any]) -> int | None:
        value = payload.get("out_path_len", payload.get("path_len"))
        try:
            hops = int(value)
        except (TypeError, ValueError):
            return None
        if hops < 0 or hops == 255:
            return None
        return hops

    def _split_route_hashes(self, path: Any, hash_mode: Any, hops: int | None) -> list[str]:
        if not isinstance(path, str) or not path:
            return []
        try:
            hash_size_bytes = int(hash_mode) + 1
        except (TypeError, ValueError):
            hash_size_bytes = 1
        if hash_size_bytes <= 0:
            hash_size_bytes = 1
        chunk_size = hash_size_bytes * 2
        hashes = [path[index : index + chunk_size] for index in range(0, len(path), chunk_size)]
        hashes = [item for item in hashes if item]
        if hops is not None:
            hashes = hashes[:hops]
        return hashes

    def _meshcore_timestamp(self, value: Any) -> datetime | None:
        try:
            timestamp = int(value)
        except (TypeError, ValueError):
            return None
        if timestamp <= 0:
            return None
        parsed = datetime.fromtimestamp(timestamp, UTC)
        if parsed > datetime.now(UTC) + timedelta(days=1):
            return None
        return parsed

    def _contact_type_label(self, value: Any) -> str:
        labels = {
            0: "Unknown",
            1: "Client",
            2: "Repeater",
            3: "Room Server",
            4: "Sensor",
        }
        try:
            contact_type = int(value)
        except (TypeError, ValueError):
            return "Unknown"
        return labels.get(contact_type, f"Unknown (type {contact_type})")

    def _valid_contact(self, contact: dict[str, Any]) -> bool:
        public_key = str(contact.get("public_key") or "")
        if not re.fullmatch(r"[0-9a-fA-F]{64}", public_key):
            return False
        try:
            contact_type = int(contact.get("type"))
        except (TypeError, ValueError):
            return False
        if contact_type not in {0, 1, 2, 3, 4}:
            return False
        name = contact.get("adv_name")
        if isinstance(name, str) and any(ord(char) < 32 for char in name):
            return False
        latitude = contact.get("adv_lat")
        longitude = contact.get("adv_lon")
        if latitude not in (None, 0, 0.0):
            try:
                if not -90 <= float(latitude) <= 90:
                    return False
            except (TypeError, ValueError):
                return False
        if longitude not in (None, 0, 0.0):
            try:
                if not -180 <= float(longitude) <= 180:
                    return False
            except (TypeError, ValueError):
                return False
        return True

    async def _get_or_create_node(self, session, pubkey_prefix: str) -> Node:
        result = await session.execute(
            select(Node).where((Node.meshcore_id == pubkey_prefix) | (Node.public_key.startswith(pubkey_prefix)))
        )
        node = result.scalar_one_or_none()
        if node:
            node.last_heard_at = datetime.now(UTC)
            return node

        node = Node(
            meshcore_id=pubkey_prefix,
            public_key=pubkey_prefix,
            short_name=pubkey_prefix[:6].upper(),
            display_name=pubkey_prefix[:6].upper(),
            status="online",
            first_seen_at=datetime.now(UTC),
            last_heard_at=datetime.now(UTC),
            raw_info={"source": "incoming_message", "pubkey_prefix": pubkey_prefix},
        )
        session.add(node)
        await session.flush()
        return node
