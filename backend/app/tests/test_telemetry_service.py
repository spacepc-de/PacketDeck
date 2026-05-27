from app.services.telemetry_service import normalize_gateway_telemetry


def test_normalize_gateway_telemetry_preserves_raw_payload():
    payload = {"battery_percentage": "94.67", "unknown_field": "kept"}

    normalized = normalize_gateway_telemetry(payload)

    assert str(normalized["battery_percentage"]) == "94.67"
    assert normalized["raw_payload"] == payload
