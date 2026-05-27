from decimal import Decimal, InvalidOperation
from typing import Any

TELEMETRY_FIELD_MAP = {
    "bandwidth": ("bandwidth_khz", Decimal),
    "bandwidth_khz": ("bandwidth_khz", Decimal),
    "battery_percentage": ("battery_percentage", Decimal),
    "battery_voltage": ("battery_voltage_v", Decimal),
    "battery_voltage_v": ("battery_voltage_v", Decimal),
    "ch1_voltage": ("ch1_voltage_v", Decimal),
    "ch1_voltage_v": ("ch1_voltage_v", Decimal),
    "companion_prefix": ("companion_prefix", str),
    "frequency": ("frequency_mhz", Decimal),
    "frequency_mhz": ("frequency_mhz", Decimal),
    "last_message_delivery": ("last_message_delivery", str),
    "latitude": ("latitude", Decimal),
    "longitude": ("longitude", Decimal),
    "node_count": ("node_count", int),
    "node_status": ("node_status", str),
    "request_rate_limiter": ("request_rate_limiter_tokens", Decimal),
    "request_rate_limiter_tokens": ("request_rate_limiter_tokens", Decimal),
    "spreading_factor": ("spreading_factor", int),
    "tx_power": ("tx_power_dbm", Decimal),
    "tx_power_dbm": ("tx_power_dbm", Decimal),
    "uptime_seconds": ("uptime_seconds", int),
    "last_rssi": ("last_rssi", Decimal),
    "last_snr": ("last_snr", Decimal),
}


def normalize_gateway_telemetry(payload: dict[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {"raw_payload": payload.get("raw_payload", payload)}
    for source_key, (target_key, converter) in TELEMETRY_FIELD_MAP.items():
        if source_key not in payload or payload[source_key] is None:
            continue
        try:
            normalized[target_key] = converter(str(payload[source_key])) if converter is Decimal else converter(payload[source_key])
        except (InvalidOperation, ValueError, TypeError):
            continue
    return normalized
