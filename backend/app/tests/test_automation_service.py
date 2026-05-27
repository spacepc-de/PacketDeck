import uuid

from app.db.models import AutomationRule
from app.services.automation_service import (
    _has_other_matching_automation,
    _is_chatbot_catch_all_rule,
    _openai_user_message,
    trigger_matches,
)


def test_message_matches_trigger_is_case_insensitive_by_default():
    rule = {"trigger_type": "message.matches", "trigger_config": {"pattern": "^weather$"}}

    assert trigger_matches(rule, "message.received", {"body": "Weather"})


def test_openai_command_mode_uses_text_after_command():
    action = {"chat_mode": "command", "command": "!chat"}

    assert _openai_user_message(action, {"body": "!chat explain meshcore"}) == "explain meshcore"


def test_openai_command_mode_requires_text_after_command():
    action = {"chat_mode": "command", "command": "!chat"}

    assert _openai_user_message(action, {"body": "!chat"}) == ""


def test_chatbot_catch_all_yields_to_specific_automation():
    chatbot_rule = AutomationRule(
        id=uuid.uuid4(),
        name="Chatbot",
        enabled=True,
        trigger_type="message.received",
        trigger_config={},
        conditions=[],
        actions=[{"type": "openai.chat_reply", "chat_mode": "chatbot"}],
    )
    command_rule = AutomationRule(
        id=uuid.uuid4(),
        name="Command",
        enabled=True,
        trigger_type="message.matches",
        trigger_config={"pattern": "^!status$"},
        conditions=[],
        actions=[{"type": "meshcore.reply", "body": "ok"}],
    )

    assert _is_chatbot_catch_all_rule(chatbot_rule)
    assert _has_other_matching_automation(chatbot_rule, [chatbot_rule, command_rule])
