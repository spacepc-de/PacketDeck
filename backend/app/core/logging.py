import logging
import sys

from pythonjsonlogger.json import JsonFormatter

SECRET_KEYS = ("password", "token", "secret", "pin", "api_key")


class SecretRedactionFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, dict):
            record.msg = redact_secrets(record.msg)
        return True


def redact_secrets(value):
    if isinstance(value, dict):
        return {
            key: "***" if any(secret in key.lower() for secret in SECRET_KEYS) else redact_secrets(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_secrets(item) for item in value]
    return value


def configure_logging() -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    handler.addFilter(SecretRedactionFilter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(logging.INFO)
