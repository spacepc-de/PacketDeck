import re
import ssl
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlparse

import aiomqtt
import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.db.models import AutomationRule, AutomationRun, GatewayTelemetry, Message, MqttBroker, Node
from app.meshcore.models import MessageSendRequest
from app.services.webhook_service import is_private_webhook_target


def trigger_matches(rule: dict[str, Any], event_type: str, payload: dict[str, Any]) -> bool:
    trigger_type = rule.get("trigger_type")
    if trigger_type == event_type:
        return True
    if trigger_type == "message.matches" and event_type == "message.received":
        config = rule.get("trigger_config", {})
        pattern = config.get("pattern")
        if not pattern:
            return False
        flags = 0 if config.get("case_sensitive") else re.IGNORECASE
        return re.search(pattern, str(payload.get("body", "")), flags) is not None
    return False


async def process_automation_event(
    session: AsyncSession,
    settings: Settings,
    event_type: str,
    payload: dict[str, Any],
    manager: Any | None = None,
) -> list[AutomationRun]:
    result = await session.execute(
        select(AutomationRule).where(AutomationRule.enabled.is_(True)).order_by(AutomationRule.created_at.asc())
    )
    rules = result.scalars().all()
    matched_rules: list[AutomationRule] = []
    for rule in rules:
        if not trigger_matches(_rule_dict(rule), event_type, payload):
            continue
        if not _conditions_match(rule.conditions or [], payload):
            continue
        matched_rules.append(rule)

    runs: list[AutomationRun] = []
    for rule in matched_rules:
        if _is_chatbot_catch_all_rule(rule) and _has_other_matching_automation(rule, matched_rules):
            continue
        if await _cooldown_active(session, rule):
            continue

        run = AutomationRun(
            rule_id=rule.id,
            status="running",
            trigger_payload=payload,
            action_results=[],
        )
        session.add(run)
        await session.flush()

        try:
            action_results = []
            for action in rule.actions or []:
                action_results.append(await _run_action(session, settings, action, payload, manager))
            run.status = "completed"
            run.action_results = action_results
        except Exception as exc:
            run.status = "failed"
            run.error_message = str(exc)
        finally:
            run.finished_at = datetime.now(UTC)
            runs.append(run)

    await session.commit()
    return runs


async def test_automation_rule(
    session: AsyncSession,
    settings: Settings,
    rule: AutomationRule,
    payload: dict[str, Any] | None = None,
    manager: Any | None = None,
) -> AutomationRun:
    test_payload = payload or {
        "body": "test",
        "from_node_id": None,
        "from_meshcore_id": None,
        "channel": None,
        "raw_payload": {},
        "test": True,
    }
    run = AutomationRun(
        rule_id=rule.id,
        status="running",
        trigger_payload=test_payload,
        action_results=[],
    )
    session.add(run)
    await session.flush()
    try:
        results = []
        for action in rule.actions or []:
            results.append(await _run_action(session, settings, action, test_payload, manager))
        run.status = "completed"
        run.action_results = results
    except Exception as exc:
        run.status = "failed"
        run.error_message = str(exc)
    finally:
        run.finished_at = datetime.now(UTC)
    await session.commit()
    await session.refresh(run)
    return run


def _rule_dict(rule: AutomationRule) -> dict[str, Any]:
    return {
        "trigger_type": rule.trigger_type,
        "trigger_config": rule.trigger_config or {},
    }


def _conditions_match(conditions: list[dict[str, Any]], payload: dict[str, Any]) -> bool:
    for condition in conditions:
        condition_type = condition.get("type")
        if condition_type == "sender.equals":
            expected = condition.get("node_id")
            if expected and expected not in {payload.get("from_node_id"), payload.get("from_meshcore_id")}:
                return False
        elif condition_type == "channel.equals":
            expected = condition.get("channel")
            if expected not in (None, "") and str(payload.get("channel")) != str(expected):
                return False
        elif condition_type == "message.contains":
            text = str(condition.get("text", ""))
            body = str(payload.get("body", ""))
            if condition.get("case_sensitive"):
                if text not in body:
                    return False
            elif text.lower() not in body.lower():
                return False
        elif condition_type == "message.regex":
            flags = 0 if condition.get("case_sensitive") else re.IGNORECASE
            if not re.search(str(condition.get("pattern", "")), str(payload.get("body", "")), flags):
                return False
    return True


def _is_chatbot_catch_all_rule(rule: AutomationRule) -> bool:
    if rule.trigger_type != "message.received":
        return False
    return any(
        action.get("type") == "openai.chat_reply" and action.get("chat_mode") == "chatbot"
        for action in rule.actions or []
    )


def _has_other_matching_automation(rule: AutomationRule, matched_rules: list[AutomationRule]) -> bool:
    for other in matched_rules:
        if other.id == rule.id:
            continue
        if _is_chatbot_catch_all_rule(other):
            continue
        return True
    return False


async def _cooldown_active(session: AsyncSession, rule: AutomationRule) -> bool:
    if not rule.cooldown_seconds:
        return False
    cutoff = datetime.now(UTC) - timedelta(seconds=rule.cooldown_seconds)
    result = await session.execute(
        select(AutomationRun)
        .where(
            AutomationRun.rule_id == rule.id,
            AutomationRun.started_at >= cutoff,
            AutomationRun.status == "completed",
        )
        .limit(1)
    )
    return result.scalar_one_or_none() is not None


async def _run_action(
    session: AsyncSession,
    settings: Settings,
    action: dict[str, Any],
    payload: dict[str, Any],
    manager: Any | None = None,
) -> dict[str, Any]:
    action_type = action.get("type")
    if action_type == "mqtt.publish":
        return await _publish_mqtt(session, settings, action, payload)
    if action_type == "webhook.call":
        return await _call_webhook(action, payload)
    if action_type == "meshcore.reply":
        return await _meshcore_reply(action, payload, manager)
    if action_type == "openai.chat_reply":
        return await _openai_chat_reply(session, settings, action, payload, manager)
    if action_type == "system.log":
        return {"type": action_type, "status": "completed", "message": action.get("message", "Logged")}
    raise ValueError(f"Unsupported automation action: {action_type}")


async def _meshcore_reply(action: dict[str, Any], payload: dict[str, Any], manager: Any | None) -> dict[str, Any]:
    body = _render_template(str(action.get("body") or ""), payload).strip()
    if not body:
        raise ValueError("Reply body is required")
    return await _send_reply(body, action, payload, manager, "meshcore.reply")


async def _openai_chat_reply(
    session: AsyncSession,
    settings: Settings,
    action: dict[str, Any],
    payload: dict[str, Any],
    manager: Any | None,
) -> dict[str, Any]:
    if not settings.openai_api_key:
        raise ValueError("OPENAI_API_KEY is not configured")
    user_message = _openai_user_message(action, payload)
    if not user_message:
        raise ValueError("Incoming message body is empty")
    model = str(action.get("model") or settings.openai_model)
    system_prompt = str(
        action.get("system_prompt")
        or "You are PacketDeck, a concise radio messaging assistant. Reply briefly and use plain text only."
    )
    if action.get("include_packetdeck_context", True):
        system_prompt = f"{system_prompt}\n\n{await _packetdeck_context_summary(session, manager, payload)}"
    configured_max = int(action.get("max_output_chars") or settings.meshcore_message_max_chars)
    max_output_chars = min(configured_max, settings.meshcore_message_max_chars)
    response_text = await _create_openai_response(
        api_key=settings.openai_api_key.get_secret_value(),
        model=model,
        system_prompt=system_prompt,
        user_message=user_message,
    )
    response_text = response_text.strip()
    response_text = _truncate_message(response_text, max_output_chars)
    send_result = await _send_reply(response_text, action, payload, manager, "openai.chat_reply")
    return {**send_result, "model": model}


async def _packetdeck_context_summary(session: AsyncSession, manager: Any | None, payload: dict[str, Any]) -> str:
    lines = [
        "PacketDeck context:",
        "- You can answer questions about the local MeshCore gateway, known clients/nodes, telemetry, hops, and routes using only this context.",
        "- If a value is missing, say that PacketDeck does not have it yet.",
        "- Privacy rule: do not reveal message contents, message summaries, or conversations from other nodes or channels.",
        "- Only discuss message content when it is the current incoming user message or explicitly from the same requesting node/channel context.",
    ]

    if manager is not None:
        state = getattr(manager, "state", None)
        if state is not None:
            lines.append(
                "- Gateway: "
                f"connection={_value(getattr(state, 'state', None))}, "
                f"type={_value(getattr(state, 'connection_type', None))}, "
                f"device={_value(getattr(state, 'device_identifier', None))}, "
                f"firmware={_value(getattr(state, 'firmware_version', None))}, "
                f"last_error={_value(getattr(state, 'last_error', None))}"
            )
        latest = getattr(manager, "latest_gateway_telemetry", None)
        if isinstance(latest, dict) and latest:
            lines.append(f"- Latest live telemetry: {_compact_mapping(latest, 12)}")

    result = await session.execute(select(GatewayTelemetry).order_by(GatewayTelemetry.recorded_at.desc()).limit(1))
    telemetry = result.scalar_one_or_none()
    if telemetry:
        lines.append(
            "- Latest stored gateway telemetry: "
            f"recorded_at={_dt(telemetry.recorded_at)}, "
            f"battery={_num(telemetry.battery_percentage)}%, "
            f"voltage={_num(telemetry.battery_voltage_v)}V, "
            f"ch1={_num(telemetry.ch1_voltage_v)}V, "
            f"nodes={_value(telemetry.node_count)}, "
            f"node_status={_value(telemetry.node_status)}, "
            f"delivery={_value(telemetry.last_message_delivery)}, "
            f"frequency={_num(telemetry.frequency_mhz)}MHz, "
            f"bandwidth={_num(telemetry.bandwidth_khz)}kHz, "
            f"sf={_value(telemetry.spreading_factor)}, "
            f"tx={_num(telemetry.tx_power_dbm)}dBm, "
            f"rssi={_num(telemetry.last_rssi)}, "
            f"snr={_num(telemetry.last_snr)}"
        )

    result = await session.execute(select(Node).order_by(Node.last_heard_at.desc().nullslast(), Node.updated_at.desc()).limit(20))
    nodes = result.scalars().all()
    if nodes:
        lines.append(f"- Known nodes ({len(nodes)} shown, newest heard first):")
        for node in nodes:
            lines.append(
                "  - "
                f"name={_value(node.display_name or node.long_name or node.short_name)}, "
                f"meshcore_id={_value(node.meshcore_id)}, "
                f"public_key={_value(node.public_key)}, "
                f"role={_value(node.role)}, "
                f"status={_value(node.status)}, "
                f"last_heard={_dt(node.last_heard_at)}, "
                f"battery={_num(node.battery_percentage)}%, "
                f"voltage={_num(node.battery_voltage_v)}V, "
                f"hops={_route_value(node, 'hops')}, "
                f"route={_route_value(node, 'path_display')}, "
                f"location={_location(node.latitude, node.longitude)}, "
                f"hardware={_value(node.hardware_model)}, "
                f"firmware={_value(node.firmware_version)}"
            )
    else:
        lines.append("- Known nodes: none stored yet.")

    lines.extend(await _requester_message_context(session, payload))

    return "\n".join(lines)


async def _requester_message_context(session: AsyncSession, payload: dict[str, Any]) -> list[str]:
    lines = ["- Message privacy: global message history is intentionally not included."]
    node_id = payload.get("from_node_id")
    channel = payload.get("channel")
    filters = []
    if node_id:
        filters.append((Message.from_node_id == node_id) | (Message.to_node_id == node_id))
    elif channel not in (None, ""):
        filters.append(Message.channel == str(channel))
    if not filters:
        return lines

    result = await session.execute(
        select(Message)
        .where(filters[0])
        .order_by(Message.received_at.desc().nullslast(), Message.sent_at.desc().nullslast())
        .limit(4)
    )
    messages = result.scalars().all()
    if not messages:
        return lines

    lines.append("- Same conversation recent messages:")
    for message in messages:
        lines.append(
            "  - "
            f"time={_dt(message.received_at or message.sent_at)}, "
            f"direction={message.direction}, "
            f"channel={_value(message.channel)}, "
            f"status={_value(message.status)}, "
            f"body={_clip(message.body, 80)}"
        )
    return lines


def _compact_mapping(value: dict[str, Any], limit: int) -> str:
    parts = []
    for key in sorted(value.keys())[:limit]:
        item = value.get(key)
        if isinstance(item, (dict, list)):
            continue
        parts.append(f"{key}={_clip(str(item), 40)}")
    return ", ".join(parts) if parts else "unavailable"


def _location(latitude: Any, longitude: Any) -> str:
    if latitude is None or longitude is None:
        return "unavailable"
    return f"{_num(latitude)},{_num(longitude)}"


def _route_value(node: Node, key: str) -> str:
    raw_info = node.raw_info if isinstance(node.raw_info, dict) else {}
    route = raw_info.get("route") if isinstance(raw_info.get("route"), dict) else {}
    return _value(route.get(key))


def _dt(value: Any) -> str:
    if value is None:
        return "unavailable"
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat()
    return str(value)


def _num(value: Any) -> str:
    if value is None:
        return "unavailable"
    try:
        return f"{float(value):.2f}".rstrip("0").rstrip(".")
    except (TypeError, ValueError):
        return str(value)


def _value(value: Any) -> str:
    if value is None or value == "":
        return "unavailable"
    return _clip(str(value), 80)


def _clip(value: str, limit: int) -> str:
    clean = " ".join(value.split())
    if len(clean) <= limit:
        return clean
    return clean[: limit - 3].rstrip() + "..."


def _openai_user_message(action: dict[str, Any], payload: dict[str, Any]) -> str:
    body = str(payload.get("body") or "").strip()
    if action.get("chat_mode") != "command":
        return body

    command = str(action.get("command") or "!chat").strip()
    if not command:
        return body
    if body.lower() == command.lower():
        return ""
    if body.lower().startswith(f"{command.lower()} "):
        return body[len(command) :].strip()
    return body


async def _create_openai_response(api_key: str, model: str, system_prompt: str, user_message: str) -> str:
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            "https://api.openai.com/v1/responses",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": model,
                "instructions": system_prompt,
                "input": user_message,
            },
        )
        response.raise_for_status()
    data = response.json()
    output_text = data.get("output_text")
    if isinstance(output_text, str) and output_text.strip():
        return output_text
    for item in data.get("output", []):
        for content in item.get("content", []):
            text = content.get("text")
            if isinstance(text, str) and text.strip():
                return text
    raise ValueError("OpenAI response did not contain text")


async def _send_reply(
    body: str,
    action: dict[str, Any],
    payload: dict[str, Any],
    manager: Any | None,
    action_type: str,
) -> dict[str, Any]:
    if manager is None:
        raise ValueError("MeshCore manager is not available")
    message_limit = getattr(manager.settings, "meshcore_message_max_chars", 180)
    body = _truncate_message(body, message_limit)
    channel = payload.get("channel")
    allow_channel_reply = bool(action.get("allow_channel_reply", False))
    if channel not in (None, "") and not allow_channel_reply:
        return {
            "type": action_type,
            "status": "skipped",
            "reason": "Public channel replies are disabled for this action",
            "sent_to": None,
            "channel": str(channel),
        }
    to_node_id = action.get("to_node_id") or payload.get("from_meshcore_id") or payload.get("from_node_id")
    request = MessageSendRequest(
        to_node_id=str(to_node_id) if to_node_id and channel in (None, "") else None,
        channel=str(channel) if channel not in (None, "") else None,
        body=body,
        expect_ack=False if channel not in (None, "") else bool(action.get("expect_ack", True)),
    )
    result = await manager.send_message(request)
    return {
        "type": action_type,
        "status": "completed",
        "sent_to": request.to_node_id,
        "channel": request.channel,
        "meshcore_message_id": result.get("meshcore_message_id"),
    }


def _truncate_message(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    if limit <= 3:
        return value[:limit]
    return value[: limit - 3].rstrip() + "..."


async def _publish_mqtt(
    session: AsyncSession,
    settings: Settings,
    action: dict[str, Any],
    payload: dict[str, Any],
) -> dict[str, Any]:
    topic = _render_template(str(action.get("topic") or "meshcore-webgui/automations/message"), payload)
    message = _render_payload(action.get("payload", {"body": "{{body}}"}), payload)
    broker = await _get_broker(session, action.get("broker_id"))
    host, port = _mqtt_host_port(settings, broker)

    async with aiomqtt.Client(
        hostname=host,
        port=port,
        username=broker.username if broker else None,
        password=broker.password_secret_ref if broker else None,
        identifier=broker.client_id if broker else None,
        tls_context=ssl.create_default_context() if broker and broker.tls_enabled else None,
    ) as client:
        await client.publish(topic, payload=message, qos=int(action.get("qos", 0)), retain=bool(action.get("retain", False)))
    return {"type": "mqtt.publish", "status": "completed", "topic": topic}


async def _call_webhook(action: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    url = str(action.get("url") or "")
    if not url:
        raise ValueError("Webhook URL is required")
    if is_private_webhook_target(url) and not action.get("allow_private_network"):
        raise ValueError("Webhook target is private. Enable private network calls explicitly for this rule.")
    body = _render_payload(action.get("payload", {"body": "{{body}}"}), payload)
    method = str(action.get("method") or "POST").upper()
    headers = action.get("headers") if isinstance(action.get("headers"), dict) else {}
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.request(method, url, content=body, headers=headers)
        response.raise_for_status()
    return {"type": "webhook.call", "status": "completed", "url": url, "status_code": response.status_code}


async def _get_broker(session: AsyncSession, broker_id: str | None) -> MqttBroker | None:
    if broker_id:
        try:
            import uuid

            return await session.get(MqttBroker, uuid.UUID(str(broker_id)))
        except ValueError:
            return None
    result = await session.execute(select(MqttBroker).order_by(MqttBroker.created_at.desc()).limit(1))
    return result.scalar_one_or_none()


def _mqtt_host_port(settings: Settings, broker: MqttBroker | None) -> tuple[str, int]:
    if broker:
        return broker.host, broker.port
    parsed = urlparse(settings.mqtt_url)
    return parsed.hostname or "localhost", parsed.port or 1883


def _render_payload(value: Any, payload: dict[str, Any]) -> str:
    if isinstance(value, str):
        return _render_template(value, payload)
    import json

    return json.dumps(_render_object(value, payload))


def _render_object(value: Any, payload: dict[str, Any]) -> Any:
    if isinstance(value, str):
        return _render_template(value, payload)
    if isinstance(value, list):
        return [_render_object(item, payload) for item in value]
    if isinstance(value, dict):
        return {key: _render_object(item, payload) for key, item in value.items()}
    return value


def _render_template(template: str, payload: dict[str, Any]) -> str:
    rendered = template
    for key, value in payload.items():
        if isinstance(value, (str, int, float)) or value is None:
            rendered = rendered.replace(f"{{{{{key}}}}}", "" if value is None else str(value))
    return rendered
