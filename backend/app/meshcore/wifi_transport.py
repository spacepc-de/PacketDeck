from collections.abc import AsyncIterator
import asyncio
from enum import Enum
from typing import Any

from meshcore import MeshCore
from meshcore.events import EventType

from app.meshcore.events import MeshCoreEvent
from app.meshcore.transports import MeshCoreTransport

RADIO_PRESETS: tuple[dict[str, Any], ...] = (
    {"id": "au", "label": "Australia", "frequency_mhz": 915.800, "bandwidth_khz": 250.0, "spreading_factor": 11, "coding_rate": 5, "tx_power_dbm": 20, "band": "915 MHz"},
    {"id": "au_narrow", "label": "Australia (Narrow)", "frequency_mhz": 916.575, "bandwidth_khz": 62.5, "spreading_factor": 7, "coding_rate": 5, "tx_power_dbm": 20, "band": "915 MHz"},
    {"id": "au_sa_wa_qld", "label": "Australia SA, WA, QLD", "frequency_mhz": 923.125, "bandwidth_khz": 62.5, "spreading_factor": 8, "coding_rate": 5, "tx_power_dbm": 20, "band": "915 MHz"},
    {"id": "cz", "label": "Czech Republic", "frequency_mhz": 869.432, "bandwidth_khz": 62.5, "spreading_factor": 7, "coding_rate": 5, "tx_power_dbm": 14, "band": "868 MHz"},
    {"id": "eu_433", "label": "EU 433 MHz", "frequency_mhz": 433.650, "bandwidth_khz": 250.0, "spreading_factor": 11, "coding_rate": 5, "tx_power_dbm": 20, "band": "433 MHz"},
    {"id": "eu_uk_long", "label": "EU/UK (Long Range)", "frequency_mhz": 869.525, "bandwidth_khz": 250.0, "spreading_factor": 11, "coding_rate": 5, "tx_power_dbm": 14, "band": "868 MHz"},
    {"id": "eu_uk_medium", "label": "EU/UK (Medium Range)", "frequency_mhz": 869.525, "bandwidth_khz": 250.0, "spreading_factor": 10, "coding_rate": 5, "tx_power_dbm": 14, "band": "868 MHz"},
    {"id": "eu_uk_narrow", "label": "EU/UK (Narrow)", "frequency_mhz": 869.618, "bandwidth_khz": 62.5, "spreading_factor": 8, "coding_rate": 5, "tx_power_dbm": 14, "band": "868 MHz"},
    {"id": "nz", "label": "New Zealand", "frequency_mhz": 917.375, "bandwidth_khz": 250.0, "spreading_factor": 11, "coding_rate": 5, "tx_power_dbm": 20, "band": "915 MHz"},
    {"id": "nz_narrow", "label": "New Zealand (Narrow)", "frequency_mhz": 917.375, "bandwidth_khz": 62.5, "spreading_factor": 7, "coding_rate": 5, "tx_power_dbm": 20, "band": "915 MHz"},
    {"id": "pt_433", "label": "Portugal 433", "frequency_mhz": 433.375, "bandwidth_khz": 62.5, "spreading_factor": 9, "coding_rate": 5, "tx_power_dbm": 20, "band": "433 MHz"},
    {"id": "pt_869", "label": "Portugal 869", "frequency_mhz": 869.618, "bandwidth_khz": 62.5, "spreading_factor": 7, "coding_rate": 5, "tx_power_dbm": 14, "band": "868 MHz"},
    {"id": "ch", "label": "Switzerland", "frequency_mhz": 869.618, "bandwidth_khz": 62.5, "spreading_factor": 8, "coding_rate": 5, "tx_power_dbm": 14, "band": "868 MHz"},
    {"id": "us_az", "label": "USA Arizona", "frequency_mhz": 908.205, "bandwidth_khz": 62.5, "spreading_factor": 10, "coding_rate": 5, "tx_power_dbm": 20, "band": "915 MHz"},
    {"id": "us_ca", "label": "USA/Canada", "frequency_mhz": 910.525, "bandwidth_khz": 62.5, "spreading_factor": 7, "coding_rate": 5, "tx_power_dbm": 20, "band": "915 MHz"},
    {"id": "us_ne", "label": "USA Nebraska", "frequency_mhz": 910.525, "bandwidth_khz": 62.5, "spreading_factor": 9, "coding_rate": 8, "tx_power_dbm": 22, "band": "915 MHz"},
    {"id": "us_sac_foothills", "label": "USA Sacramento-Foothills", "frequency_mhz": 909.875, "bandwidth_khz": 62.5, "spreading_factor": 9, "coding_rate": 5, "tx_power_dbm": 20, "band": "915 MHz"},
    {"id": "us_socal", "label": "USA Southern California", "frequency_mhz": 927.875, "bandwidth_khz": 62.5, "spreading_factor": 7, "coding_rate": 5, "tx_power_dbm": 20, "band": "915 MHz"},
    {"id": "vn", "label": "Vietnam", "frequency_mhz": 920.250, "bandwidth_khz": 250.0, "spreading_factor": 11, "coding_rate": 5, "tx_power_dbm": 20, "band": "915 MHz"},
    {"id": "offgrid_433", "label": "Off-Grid 433", "frequency_mhz": 433.000, "bandwidth_khz": 250.0, "spreading_factor": 11, "coding_rate": 5, "tx_power_dbm": 20, "band": "433 MHz"},
    {"id": "offgrid_869", "label": "Off-Grid 869", "frequency_mhz": 869.000, "bandwidth_khz": 250.0, "spreading_factor": 11, "coding_rate": 5, "tx_power_dbm": 14, "band": "868 MHz"},
    {"id": "offgrid_918", "label": "Off-Grid 918", "frequency_mhz": 918.000, "bandwidth_khz": 250.0, "spreading_factor": 11, "coding_rate": 5, "tx_power_dbm": 20, "band": "915 MHz"},
)
RADIO_PRESETS_BY_ID = {str(preset["id"]): preset for preset in RADIO_PRESETS}


class WifiTcpMeshCoreTransport(MeshCoreTransport):
    def __init__(self, host: str, port: int) -> None:
        self.host = host
        self.tcp_port = port
        self.port = f"{host}:{port}"
        self._connected = False
        self._client: MeshCore | None = None
        self._device_info: dict[str, Any] = {}
        self._self_info: dict[str, Any] = {}
        self._event_queue: asyncio.Queue[MeshCoreEvent] = asyncio.Queue(maxsize=1000)
        self._event_subscription = None
        self._auto_message_fetch_subscription = None
        self._messages_waiting_subscription = None
        self._pending_message_task: asyncio.Task | None = None
        self._message_retry_tasks: set[asyncio.Task] = set()
        self._message_sweep_task: asyncio.Task | None = None
        self._message_drain_lock = asyncio.Lock()
        self._command_lock = asyncio.Lock()
        self._original_get_msg = None

    async def connect(self) -> None:
        client = await asyncio.wait_for(
            MeshCore.create_tcp(
                self.host,
                self.tcp_port,
                auto_reconnect=True,
                max_reconnect_attempts=5,
            ),
            timeout=12,
        )
        if client is None:
            raise ConnectionError(f"MeshCore WiFi TCP companion did not respond at {self.host}:{self.tcp_port}")
        self._client = client
        self._event_subscription = self._client.subscribe(None, self._queue_meshcore_event)
        self._connected = True
        await self._start_official_message_fetching()

    async def disconnect(self) -> None:
        if self._client:
            await self._stop_official_message_fetching()
            if self._event_subscription:
                self._event_subscription.unsubscribe()
                self._event_subscription = None
            if self._pending_message_task:
                self._pending_message_task.cancel()
                self._pending_message_task = None
            for task in self._message_retry_tasks:
                task.cancel()
            self._message_retry_tasks.clear()
            if self._message_sweep_task:
                self._message_sweep_task.cancel()
                self._message_sweep_task = None
            await self._client.disconnect()
            self._client = None
            self._original_get_msg = None
        self._connected = False

    async def events(self) -> AsyncIterator[MeshCoreEvent]:
        while self._connected:
            yield await self._event_queue.get()

    async def _queue_meshcore_event(self, event) -> None:
        event_type = getattr(event.type, "value", str(event.type))
        if event_type == "messages_waiting":
            self._schedule_message_drain()
        await self._enqueue_meshcore_event(event)

    async def _enqueue_meshcore_event(self, event) -> None:
        event_type = getattr(event.type, "value", str(event.type))
        payload = self._json_safe(getattr(event, "payload", {}))
        severity = "error" if event_type in {"command_error", "login_failed"} else "info"
        meshcore_event = MeshCoreEvent(
            type="system.error" if severity == "error" else "telemetry.gateway_updated",
            source="meshcore",
            severity=severity,
            payload={
                "meshcore_event_type": event_type,
                "attributes": self._json_safe(getattr(event, "attributes", {})),
                "payload": payload,
            },
        )
        try:
            self._event_queue.put_nowait(meshcore_event)
        except asyncio.QueueFull:
            await self._event_queue.get()
            self._event_queue.put_nowait(meshcore_event)


    async def _start_official_message_fetching(self) -> None:
        if not self._client:
            return
        # meshcore_py.start_auto_message_fetching() calls get_msg() outside PacketDeck's
        # command lock. PacketDeck also polls telemetry, so parallel commands on the same
        # TCP stream can steal each other's responses. We still use the official
        # MESSAGES_WAITING event, but drain the official message queue through the
        # transport command lock.
        try:
            self._messages_waiting_subscription = self._client.subscribe(
                EventType.MESSAGES_WAITING,
                self._handle_messages_waiting,
            )
            await self._publish_transport_debug("auto_message_fetching_started", mode="locked_messages_waiting")
            self._schedule_message_drain()
        except Exception as exc:
            await self._publish_transport_debug("auto_message_fetching_failed", severity="warning", error=str(exc))

    async def _handle_messages_waiting(self, event) -> None:
        self._schedule_message_drain()

    async def _stop_official_message_fetching(self) -> None:
        if self._messages_waiting_subscription:
            self._messages_waiting_subscription.unsubscribe()
            self._messages_waiting_subscription = None
        if not self._client:
            return
        try:
            await self._client.stop_auto_message_fetching()
        except Exception:
            pass
        self._auto_message_fetch_subscription = None
        self._messages_waiting_subscription = None

    async def _publish_transport_debug(self, event_type: str, severity: str = "info", **payload: Any) -> None:
        await self._event_queue.put(
            MeshCoreEvent(
                type="system.error" if severity in {"warning", "error"} else "telemetry.gateway_updated",
                source="meshcore",
                severity=severity,
                payload={"meshcore_event_type": event_type, **payload},
            )
        )

    def _schedule_message_drain(self) -> None:
        if not self._pending_message_task:
            self._pending_message_task = asyncio.create_task(self._drain_pending_messages())
        for delay in (0.75, 2.0, 5.0):
            task = asyncio.create_task(self._delayed_message_drain(delay))
            self._message_retry_tasks.add(task)
            task.add_done_callback(self._message_retry_tasks.discard)

    async def _delayed_message_drain(self, delay: float) -> None:
        try:
            await asyncio.sleep(delay)
            if self._connected:
                await self._drain_pending_messages()
        except asyncio.CancelledError:
            raise

    async def drain_pending_messages(self) -> dict[str, Any]:
        return await self._drain_pending_messages()

    async def _drain_pending_messages(self) -> dict[str, Any]:
        if self._message_drain_lock.locked():
            return {"status": "busy", "events": []}
        async with self._message_drain_lock:
            return await self._drain_pending_messages_locked()

    async def _message_sweep_loop(self) -> None:
        try:
            while self._connected:
                await asyncio.sleep(10)
                if self._connected:
                    await self._drain_pending_messages()
        except asyncio.CancelledError:
            raise

    async def _drain_pending_messages_locked(self) -> dict[str, Any]:
        events: list[str] = []
        try:
            if not self._client or not self._connected:
                return {"status": "disconnected", "events": events}
            for _ in range(25):
                async with self._command_lock:
                    event = await self._client.commands.get_msg(timeout=8)
                event_type = getattr(event.type, "value", str(event.type))
                events.append(event_type)
                if event_type in {"contact_message", "channel_message", "contact_msg", "channel_msg"}:
                    continue
                if event_type in {"no_more_messages", "command_error", "disconnected"}:
                    break
            await self._publish_transport_debug("message_sync_result", events=events)
            return {"status": "ok", "events": events}
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            await self._publish_transport_debug("message_sync_failed", severity="warning", error=str(exc))
            return {"status": "error", "events": events, "error": str(exc)}
        finally:
            self._pending_message_task = None

    async def send_message(self, to_node_id: str | None, body: str, channel: str | None, expect_ack: bool) -> str | None:
        if not self._client or not self._connected:
            raise RuntimeError("WiFi TCP transport is not connected")
        async with self._command_lock:
            try:
                if channel not in (None, ""):
                    event = await asyncio.wait_for(self._client.commands.send_chan_msg(int(channel), body), timeout=8)
                else:
                    if not to_node_id:
                        raise RuntimeError("Direct messages require a public key or prefix")
                    event = await asyncio.wait_for(self._client.commands.send_msg(to_node_id, body), timeout=8)
            except TimeoutError:
                # MeshCore can transmit the packet but miss the companion MSG_SENT response.
                # Treat this as sent with unknown ACK id; delivery may still arrive as rx_log_data.
                return None
        if event and event.is_error():
            payload = getattr(event, "payload", {}) or {}
            detail = payload.get("reason") or payload.get("error") or "MeshCore message send failed"
            if detail == "MeshCore message send failed" and payload:
                detail = f"{detail}: {self._json_safe(payload)}"
            raise RuntimeError(str(detail))
        payload = event.payload if event else {}
        expected_ack = payload.get("expected_ack") if isinstance(payload, dict) else None
        message_id = expected_ack.hex() if isinstance(expected_ack, bytes) else None
        return str(message_id) if message_id is not None else None

    async def remove_contact(self, node_id: str) -> dict[str, Any]:
        if not self._client or not self._connected:
            raise RuntimeError("WiFi TCP transport is not connected")
        async with self._command_lock:
            event = await asyncio.wait_for(self._client.commands.remove_contact(node_id), timeout=8)
        if event and event.is_error():
            payload = event.payload if isinstance(event.payload, dict) else {}
            detail = payload.get("code_string") or payload.get("reason") or payload.get("error") or "MeshCore contact remove failed"
            if payload.get("error_code") == 2 or detail == "ERR_CODE_NOT_FOUND":
                return {"status": "not_found", "detail": detail}
            raise RuntimeError(str(detail))
        return {"status": "removed"}

    async def send_advert(self, flood: bool = False) -> dict[str, Any]:
        if not self._client or not self._connected:
            raise RuntimeError("WiFi TCP transport is not connected")
        async with self._command_lock:
            event = await asyncio.wait_for(self._client.commands.send_advert(flood=flood), timeout=8)
        self._raise_on_error(event, "MeshCore advert send failed")
        return {"status": "sent", "flood": flood}

    async def get_device_info(self) -> dict[str, Any]:
        if not self._client or not self._connected:
            return self._device_info
        async with self._command_lock:
            event = await asyncio.wait_for(self._client.commands.send_device_query(), timeout=5)
        self._raise_on_error(event, "Device query failed")
        self._device_info = dict(event.payload or {})
        return self._device_info

    async def get_self_info(self) -> dict[str, Any]:
        if not self._client or not self._connected:
            return self._self_info
        async with self._command_lock:
            event = await asyncio.wait_for(self._client.commands.send_appstart(), timeout=5)
        self._raise_on_error(event, "App start query failed")
        self._self_info = dict(event.payload or {})
        return self._self_info

    async def is_reachable(self) -> bool:
        if not self._client or not self._connected:
            return False
        return bool(getattr(self._client, "is_connected", True))

    async def get_gateway_telemetry(self) -> dict[str, Any]:
        if not self._client or not self._connected:
            raise RuntimeError("WiFi TCP transport is not connected")

        raw: dict[str, Any] = {}
        async with self._command_lock:
            try:
                event = await asyncio.wait_for(self._client.commands.send_appstart(), timeout=5)
                self._raise_on_error(event, "App start query failed")
                self._self_info = dict(event.payload or {})
                raw["self_info"] = self._self_info
            except Exception as exc:
                raw["self_info"] = {"error": str(exc)}
            for key, command in (
                ("battery", self._client.commands.get_bat),
                ("self_telemetry", self._client.commands.get_self_telemetry),
                ("stats_core", self._client.commands.get_stats_core),
                ("stats_radio", self._client.commands.get_stats_radio),
                ("stats_packets", self._client.commands.get_stats_packets),
                ("contacts", self._client.commands.get_contacts),
            ):
                try:
                    event = await asyncio.wait_for(command(), timeout=5)
                    raw[key] = event.payload or {}
                except Exception as exc:
                    raw[key] = {"error": str(exc)}

        battery_mv = raw.get("stats_core", {}).get("battery_mv") or raw.get("battery", {}).get("level")
        lpp_values = raw.get("self_telemetry", {}).get("lpp") or []
        ch1_voltage = next(
            (
                item.get("value")
                for item in lpp_values
                if item.get("channel") == 1 and item.get("type") == "voltage"
            ),
            None,
        )
        contacts = raw.get("contacts") or {}
        pubkey_pre = raw.get("self_telemetry", {}).get("pubkey_pre")

        return {
            "frequency_mhz": raw["self_info"].get("radio_freq"),
            "bandwidth_khz": raw["self_info"].get("radio_bw"),
            "spreading_factor": raw["self_info"].get("radio_sf"),
            "tx_power_dbm": raw["self_info"].get("tx_power"),
            "latitude": raw["self_info"].get("adv_lat"),
            "longitude": raw["self_info"].get("adv_lon"),
            "battery_voltage_v": round(float(battery_mv) / 1000, 3) if battery_mv else None,
            "ch1_voltage_v": ch1_voltage,
            "companion_prefix": str(pubkey_pre)[:2].upper() if pubkey_pre else None,
            "node_count": len(contacts) if isinstance(contacts, dict) else None,
            "node_status": "Online",
            "last_message_delivery": "Idle",
            "uptime_seconds": raw.get("stats_core", {}).get("uptime_secs"),
            "last_rssi": raw.get("stats_radio", {}).get("last_rssi"),
            "last_snr": raw.get("stats_radio", {}).get("last_snr"),
            "raw_payload": raw,
        }

    async def get_device_settings(self) -> list[dict[str, Any]]:
        if not self._client or not self._connected:
            return []

        self_info = await self.get_self_info()
        device_info = await self.get_device_info()
        raw = await self._read_settings_payloads(device_info)

        battery_mv = raw.get("stats_core", {}).get("battery_mv") or raw.get("battery", {}).get("level")
        battery_voltage = round(float(battery_mv) / 1000, 3) if battery_mv else None
        ch1_voltage = next(
            (
                item.get("value")
                for item in (raw.get("self_telemetry", {}).get("lpp") or [])
                if item.get("channel") == 1 and item.get("type") == "voltage"
            ),
            None,
        )
        channels = raw.get("channels", [])
        channel_summary = ", ".join(
            f"{channel['channel_idx']}: {channel.get('channel_name') or 'Unnamed'}"
            for channel in channels
        )

        settings = [
            self._setting("device_name", "Device name", "Identity", self_info.get("name"), editable=True),
            self._setting("public_key", "Public key", "Identity", self_info.get("public_key"), sensitive=True),
            self._setting("companion_prefix", "Companion prefix", "Identity", (raw.get("self_telemetry", {}).get("pubkey_pre") or "")[:2].upper() or None),
            self._setting("firmware_version", "Firmware version", "Identity", device_info.get("ver")),
            self._setting("firmware_build", "Firmware build", "Identity", device_info.get("fw_build")),
            self._setting("firmware_protocol_version", "Firmware protocol version", "Identity", device_info.get("fw ver")),
            self._setting("hardware_model", "Hardware model", "Identity", device_info.get("model")),
            self._setting("repeat_enabled", "Repeater enabled", "Identity", device_info.get("repeat")),
            self._setting("radio_preset", "Radio preset", "Radio", self._detect_radio_preset(self_info), editable=True, options=self._radio_preset_options(), description="Applies frequency, bandwidth, spreading factor, coding rate, and TX power."),
            self._setting("frequency_mhz", "Frequency", "Radio", self_info.get("radio_freq"), "MHz", editable=True, min_value=400, max_value=1000),
            self._setting("bandwidth_khz", "Bandwidth", "Radio", self_info.get("radio_bw"), "kHz", editable=True, min_value=1, max_value=500),
            self._setting("spreading_factor", "Spreading factor", "Radio", self_info.get("radio_sf"), "SF", editable=True, min_value=5, max_value=12),
            self._setting("coding_rate", "Coding rate", "Radio", self_info.get("radio_cr"), editable=True, min_value=5, max_value=8),
            self._setting("tx_power_dbm", "TX power", "Radio", self_info.get("tx_power"), "dBm", editable=True, min_value=0, max_value=self_info.get("max_tx_power")),
            self._setting("max_tx_power_dbm", "Maximum TX power", "Radio", self_info.get("max_tx_power"), "dBm"),
            self._setting("allowed_repeat_frequencies", "Allowed repeat frequencies", "Radio", self._format_allowed_freqs(raw.get("allowed_repeat_freq", {}).get("freqs"))),
            self._setting("rx_delay", "RX delay", "Radio", raw.get("tuning", {}).get("rx_delay"), editable=True),
            self._setting("airtime_factor", "Airtime factor", "Radio", raw.get("tuning", {}).get("airtime_factor"), editable=True),
            self._setting("latitude", "Latitude", "Location", self_info.get("adv_lat"), "degrees", editable=True, min_value=-90, max_value=90),
            self._setting("longitude", "Longitude", "Location", self_info.get("adv_lon"), "degrees", editable=True, min_value=-180, max_value=180),
            self._setting("advertise_location_policy", "Advertise location policy", "Location", self_info.get("adv_loc_policy"), editable=True),
            self._setting("telemetry_mode_location", "Location telemetry mode", "Location", self_info.get("telemetry_mode_loc"), editable=True),
            self._setting("battery_voltage_v", "Battery voltage", "Power", battery_voltage, "V"),
            self._setting("ch1_voltage_v", "Ch1 voltage", "Power", ch1_voltage, "V"),
            self._setting("battery_level_raw_mv", "Battery raw level", "Power", raw.get("battery", {}).get("level"), "mV"),
            self._setting("storage_used_kb", "Storage used", "Power", raw.get("battery", {}).get("used_kb"), "KB"),
            self._setting("storage_total_kb", "Storage total", "Power", raw.get("battery", {}).get("total_kb"), "KB"),
            self._setting("uptime_seconds", "Uptime", "Messaging / Network", raw.get("stats_core", {}).get("uptime_secs"), "seconds"),
            self._setting("queue_length", "Queue length", "Messaging / Network", raw.get("stats_core", {}).get("queue_len")),
            self._setting("error_count", "Error count", "Messaging / Network", raw.get("stats_core", {}).get("errors")),
            self._setting("manual_add_contacts", "Manual add contacts", "Messaging / Network", self_info.get("manual_add_contacts"), editable=True),
            self._setting("autoadd_config", "Auto-add config", "Messaging / Network", raw.get("autoadd_config", {}).get("config"), editable=True),
            self._setting("multi_acks", "Multi-ACKs", "Messaging / Network", self_info.get("multi_acks"), editable=True),
            self._setting("max_contacts", "Maximum contacts", "Messaging / Network", device_info.get("max_contacts")),
            self._setting("default_flood_scope_name", "Default flood scope", "Messaging / Network", raw.get("default_flood_scope", {}).get("scope_name") or "None"),
            self._setting("default_flood_scope_key", "Default flood scope key", "Messaging / Network", raw.get("default_flood_scope", {}).get("scope_key") or None),
            self._setting("last_rssi", "Last RSSI", "Messaging / Network", raw.get("stats_radio", {}).get("last_rssi"), "dBm"),
            self._setting("last_snr", "Last SNR", "Messaging / Network", raw.get("stats_radio", {}).get("last_snr"), "dB"),
            self._setting("noise_floor", "Noise floor", "Messaging / Network", raw.get("stats_radio", {}).get("noise_floor"), "dBm"),
            self._setting("packets_received", "Packets received", "Messaging / Network", raw.get("stats_packets", {}).get("recv")),
            self._setting("packets_sent", "Packets sent", "Messaging / Network", raw.get("stats_packets", {}).get("sent")),
            self._setting("packet_receive_errors", "Packet receive errors", "Messaging / Network", raw.get("stats_packets", {}).get("recv_errors")),
            self._setting("telemetry_mode_base", "Base telemetry mode", "Messaging / Network", self_info.get("telemetry_mode_base"), editable=True),
            self._setting("telemetry_mode_environment", "Environment telemetry mode", "Messaging / Network", self_info.get("telemetry_mode_env"), editable=True),
            self._setting("channel_summary", "Configured channels", "Messaging / Network", channel_summary or "None"),
            self._setting("max_channels", "Maximum channels", "Messaging / Network", device_info.get("max_channels")),
            self._setting("current_time", "Device time", "Messaging / Network", raw.get("time", {}).get("time"), "unix seconds", editable=True),
            self._setting("path_hash_mode", "Path hash mode", "Security", raw.get("path_hash_mode", device_info.get("path_hash_mode")), editable=True),
            self._setting("custom_vars", "Custom variables", "Security", raw.get("custom_vars") or "None"),
        ]

        for channel in channels:
            idx = channel.get("channel_idx")
            settings.extend(
                [
                    self._setting(f"channel_{idx}_name", f"Channel {idx} name", "Messaging / Network", channel.get("channel_name") or "Unnamed", editable=True),
                    self._setting(f"channel_{idx}_hash", f"Channel {idx} hash", "Messaging / Network", channel.get("channel_hash")),
                    self._setting(f"channel_{idx}_secret", f"Channel {idx} secret", "Security", "Configured", sensitive=True),
                ]
            )

        return settings

    async def request_node_telemetry(self, node_id: str) -> dict[str, Any]:
        if not self._client or not self._connected:
            raise RuntimeError("WiFi TCP transport is not connected")
        pubkey_prefix = node_id[:12]

        req_telemetry_sync = getattr(self._client.commands, "req_telemetry_sync", None)
        if req_telemetry_sync:
            telemetry: list[dict[str, Any]] | None = None
            async with self._command_lock:
                try:
                    telemetry = await asyncio.wait_for(req_telemetry_sync(node_id, min_timeout=8), timeout=20)
                except TimeoutError:
                    telemetry = None
            if telemetry:
                return self._json_safe({"pubkey_pre": pubkey_prefix, "lpp": telemetry, "source": "telemetry_response"})

        try:
            async with self._command_lock:
                event = await asyncio.wait_for(self._client.commands.send_telemetry_req(node_id), timeout=8)
                self._raise_on_error(event, "Node telemetry request failed")
            legacy_telemetry = await self._client.wait_for_event(
                EventType.TELEMETRY_RESPONSE,
                attribute_filters={"pubkey_prefix": pubkey_prefix},
                timeout=25,
            )
            if legacy_telemetry and legacy_telemetry.payload:
                payload = dict(legacy_telemetry.payload)
                payload.setdefault("pubkey_pre", pubkey_prefix)
                payload.setdefault("source", "telemetry_response")
                return self._json_safe(payload)
        except TimeoutError:
            pass

        raise RuntimeError("Node did not return telemetry")

    async def request_node_status(self, node_id: str) -> dict[str, Any]:
        if not self._client or not self._connected:
            raise RuntimeError("WiFi TCP transport is not connected")
        pubkey_prefix = node_id[:12]

        status: dict[str, Any] | None = None
        async with self._command_lock:
            try:
                status = await asyncio.wait_for(
                    self._client.commands.req_status_sync(node_id, min_timeout=8),
                    timeout=20,
                )
            except TimeoutError:
                status = None
        if status:
            return self._json_safe(status)

        try:
            async with self._command_lock:
                event = await asyncio.wait_for(self._client.commands.send_statusreq(node_id), timeout=8)
                self._raise_on_error(event, "Node status request failed")
            legacy_status = await self._client.wait_for_event(
                EventType.STATUS_RESPONSE,
                attribute_filters={"pubkey_prefix": pubkey_prefix},
                timeout=20,
            )
            if legacy_status and legacy_status.payload:
                payload = dict(legacy_status.payload)
                payload.setdefault("pubkey_pre", pubkey_prefix)
                return self._json_safe(payload)
        except TimeoutError:
            pass

        telemetry: list[dict[str, Any]] | None = None
        async with self._command_lock:
            try:
                telemetry = await asyncio.wait_for(
                    self._client.commands.req_telemetry_sync(node_id, min_timeout=8),
                    timeout=20,
                )
            except TimeoutError:
                telemetry = None
        if telemetry:
            return self._json_safe({"pubkey_pre": pubkey_prefix, "lpp": telemetry, "source": "telemetry_response"})

        try:
            async with self._command_lock:
                event = await asyncio.wait_for(self._client.commands.send_telemetry_req(node_id), timeout=8)
                self._raise_on_error(event, "Node telemetry request failed")
            legacy_telemetry = await self._client.wait_for_event(
                EventType.TELEMETRY_RESPONSE,
                attribute_filters={"pubkey_prefix": pubkey_prefix},
                timeout=20,
            )
            if legacy_telemetry and legacy_telemetry.payload:
                payload = dict(legacy_telemetry.payload)
                payload.setdefault("pubkey_pre", pubkey_prefix)
                payload.setdefault("source", "telemetry_response")
                return self._json_safe(payload)
        except TimeoutError:
            pass

        raise RuntimeError("Node did not return status or telemetry")

    async def login_node(self, node_id: str, password: str) -> dict[str, Any]:
        if not self._client or not self._connected:
            raise RuntimeError("WiFi TCP transport is not connected")
        if not password:
            raise RuntimeError("Admin password is required")
        async with self._command_lock:
            event = await asyncio.wait_for(self._client.commands.send_login(node_id, password), timeout=30)
        self._raise_on_error(event, "Remote admin login send failed")
        payload = event.payload if event else {}
        sent = self._json_safe(payload if isinstance(payload, dict) else {})
        timeout = 30
        if isinstance(payload, dict) and payload.get("suggested_timeout"):
            try:
                timeout = max(30, min(90, float(payload["suggested_timeout"]) / 800))
            except (TypeError, ValueError):
                timeout = 30

        success_wait = asyncio.create_task(self._client.wait_for_event(EventType.LOGIN_SUCCESS, timeout=timeout))
        failed_wait = asyncio.create_task(self._client.wait_for_event(EventType.LOGIN_FAILED, timeout=timeout))
        done, pending = await asyncio.wait({success_wait, failed_wait}, return_when=asyncio.FIRST_COMPLETED)
        for task in pending:
            task.cancel()
        for task in done:
            login_event = task.result()
            if not login_event:
                continue
            if login_event.type == EventType.LOGIN_SUCCESS:
                result = self._json_safe(login_event.payload or {})
                result["sent"] = sent
                return result
            if login_event.type == EventType.LOGIN_FAILED:
                raise RuntimeError(f"Remote admin login failed: {self._json_safe(login_event.payload or {})}")
        raise RuntimeError(f"Remote admin login was accepted for TX but no response arrived: {sent}")

    async def send_node_command(self, node_id: str, command: str) -> str | None:
        if not self._client or not self._connected:
            raise RuntimeError("WiFi TCP transport is not connected")
        async with self._command_lock:
            event = await asyncio.wait_for(self._client.commands.send_cmd(node_id, command), timeout=8)
        self._raise_on_error(event, "Remote admin command failed")
        payload = event.payload if event else {}
        expected_ack = payload.get("expected_ack") if isinstance(payload, dict) else None
        message_id = expected_ack.hex() if isinstance(expected_ack, bytes) else None
        return str(message_id) if message_id is not None else None

    async def update_device_settings(self, values: dict[str, Any]) -> None:
        if not self._client or not self._connected:
            raise RuntimeError("WiFi TCP transport is not connected")

        current = await self.get_self_info()

        if "device_name" in values:
            await self._client.commands.set_name(str(values["device_name"]))

        selected_preset = values.get("radio_preset")
        if selected_preset and selected_preset != "custom":
            preset = RADIO_PRESETS_BY_ID.get(str(selected_preset))
            if not preset:
                raise RuntimeError(f"Unknown radio preset: {selected_preset}")
            values = {**values, "frequency_mhz": preset["frequency_mhz"], "bandwidth_khz": preset["bandwidth_khz"], "spreading_factor": preset["spreading_factor"], "coding_rate": preset["coding_rate"], "tx_power_dbm": preset["tx_power_dbm"]}

        if "tx_power_dbm" in values:
            await self._client.commands.set_tx_power(int(values["tx_power_dbm"]))

        radio_keys = {"frequency_mhz", "bandwidth_khz", "spreading_factor", "coding_rate"}
        if radio_keys.intersection(values):
            await self._client.commands.set_radio(
                float(values.get("frequency_mhz", current.get("radio_freq"))),
                float(values.get("bandwidth_khz", current.get("radio_bw"))),
                int(values.get("spreading_factor", current.get("radio_sf"))),
                int(values.get("coding_rate", current.get("radio_cr"))),
            )

        if {"latitude", "longitude"}.intersection(values):
            await self._client.commands.set_coords(
                float(values.get("latitude", current.get("adv_lat", 0))),
                float(values.get("longitude", current.get("adv_lon", 0))),
            )

        if "rx_delay" in values or "airtime_factor" in values:
            tuning = await self._client.commands.get_tuning()
            tuning_payload = tuning.payload or {}
            await self._client.commands.set_tuning(
                int(values.get("rx_delay", tuning_payload.get("rx_delay", 0))),
                int(values.get("airtime_factor", tuning_payload.get("airtime_factor", 1000))),
            )

        if "manual_add_contacts" in values:
            await self._client.commands.set_manual_add_contacts(bool(values["manual_add_contacts"]))
        if "multi_acks" in values:
            await self._client.commands.set_multi_acks(int(values["multi_acks"]))
        if "autoadd_config" in values:
            await self._client.commands.set_autoadd_config(int(values["autoadd_config"]))
        if "telemetry_mode_base" in values:
            await self._client.commands.set_telemetry_mode_base(int(values["telemetry_mode_base"]))
        if "telemetry_mode_location" in values:
            await self._client.commands.set_telemetry_mode_loc(int(values["telemetry_mode_location"]))
        if "telemetry_mode_environment" in values:
            await self._client.commands.set_telemetry_mode_env(int(values["telemetry_mode_environment"]))
        if "advertise_location_policy" in values:
            await self._client.commands.set_advert_loc_policy(int(values["advertise_location_policy"]))
        if "current_time" in values:
            await self._client.commands.set_time(int(values["current_time"]))
        if "path_hash_mode" in values:
            await self._client.commands.set_path_hash_mode(int(values["path_hash_mode"]))

        self._self_info = await self.get_self_info()

    async def _read_settings_payloads(self, device_info: dict[str, Any]) -> dict[str, Any]:
        assert self._client is not None
        payloads: dict[str, Any] = {}
        for key, command in (
            ("battery", self._client.commands.get_bat),
            ("self_telemetry", self._client.commands.get_self_telemetry),
            ("stats_core", self._client.commands.get_stats_core),
            ("stats_radio", self._client.commands.get_stats_radio),
            ("stats_packets", self._client.commands.get_stats_packets),
            ("tuning", self._client.commands.get_tuning),
            ("time", self._client.commands.get_time),
            ("autoadd_config", self._client.commands.get_autoadd_config),
            ("default_flood_scope", self._client.commands.get_default_flood_scope),
            ("custom_vars", self._client.commands.get_custom_vars),
            ("allowed_repeat_freq", self._client.commands.get_allowed_repeat_freq),
        ):
            try:
                event = await command()
                payloads[key] = event.payload if hasattr(event, "payload") else event
            except Exception as exc:
                payloads[key] = {"error": str(exc)}

        try:
            payloads["path_hash_mode"] = await self._client.commands.get_path_hash_mode()
        except Exception:
            payloads["path_hash_mode"] = device_info.get("path_hash_mode")

        channels = []
        max_channels = int(device_info.get("max_channels") or 0)
        for idx in range(min(max_channels, 8)):
            try:
                event = await self._client.commands.get_channel(idx)
                channel = dict(event.payload or {})
                secret = channel.pop("channel_secret", None)
                if channel.get("channel_name") or idx == 0 or secret:
                    channel["secret_configured"] = bool(secret)
                    channels.append(channel)
            except Exception:
                continue
        payloads["channels"] = channels
        return payloads

    def _setting(
        self,
        key: str,
        label: str,
        category: str,
        value: Any,
        unit: str | None = None,
        *,
        editable: bool = False,
        available: bool = True,
        sensitive: bool = False,
        min_value: float | None = None,
        max_value: float | None = None,
        options: list[dict[str, str]] | None = None,
        description: str | None = None,
    ) -> dict[str, Any]:
        if sensitive and value:
            value = "********"
        return {
            "key": key,
            "label": label,
            "category": category,
            "value": value,
            "unit": unit,
            "editable": editable,
            "available": available and (value is not None or editable),
            "min_value": min_value,
            "max_value": max_value,
            "options": options,
            "description": description,
        }


    def _detect_radio_preset(self, self_info: dict[str, Any]) -> str:
        try:
            current = {
                "frequency_mhz": float(self_info.get("radio_freq")),
                "bandwidth_khz": float(self_info.get("radio_bw")),
                "spreading_factor": int(self_info.get("radio_sf")),
                "coding_rate": int(self_info.get("radio_cr")),
            }
        except (TypeError, ValueError):
            return "custom"
        for preset in RADIO_PRESETS:
            if (
                abs(current["frequency_mhz"] - float(preset["frequency_mhz"])) < 0.001
                and abs(current["bandwidth_khz"] - float(preset["bandwidth_khz"])) < 0.01
                and current["spreading_factor"] == int(preset["spreading_factor"])
                and current["coding_rate"] == int(preset["coding_rate"])
            ):
                return str(preset["id"])
        return "custom"

    def _radio_preset_options(self) -> list[dict[str, str]]:
        options = [{"value": "custom", "label": "Custom", "description": "Keep the manually configured radio parameters."}]
        for preset in RADIO_PRESETS:
            options.append(
                {
                    "value": str(preset["id"]),
                    "label": str(preset["label"]),
                    "description": (
                        f"{preset['frequency_mhz']:.3f} MHz / BW {preset['bandwidth_khz']:g} kHz / "
                        f"SF{preset['spreading_factor']} / CR{preset['coding_rate']} / TX {preset['tx_power_dbm']} dBm"
                    ),
                }
            )
        return options

    def _format_allowed_freqs(self, freqs: list[dict[str, Any]] | None) -> str | None:
        if not freqs:
            return None
        return ", ".join(f"{item.get('min')}-{item.get('max')} kHz" for item in freqs)

    def _raise_on_error(self, event, fallback: str) -> None:
        if event and event.is_error():
            payload = getattr(event, "payload", {}) or {}
            raise RuntimeError(str(payload.get("reason") or payload.get("error") or fallback))

    def _json_safe(self, value: Any) -> Any:
        if isinstance(value, bytes):
            return value.hex()
        if isinstance(value, Enum):
            return value.value
        if isinstance(value, dict):
            return {str(key): self._json_safe(item) for key, item in value.items()}
        if isinstance(value, list):
            return [self._json_safe(item) for item in value]
        if isinstance(value, tuple):
            return [self._json_safe(item) for item in value]
        return value
