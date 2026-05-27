from app.core.config import Settings


def topic(settings: Settings, suffix: str) -> str:
    return f"{settings.mqtt_topic_prefix.rstrip('/')}/{suffix.lstrip('/')}"
