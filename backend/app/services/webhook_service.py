from urllib.parse import urlparse


def is_private_webhook_target(url: str) -> bool:
    hostname = urlparse(url).hostname or ""
    return hostname in {"localhost", "127.0.0.1", "::1"} or hostname.startswith("10.") or hostname.startswith("192.168.")
