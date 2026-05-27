from fastapi import Header, HTTPException, status

from app.core.config import get_settings


async def require_api_token(authorization: str | None = Header(default=None)) -> None:
    settings = get_settings()
    if not settings.auth_enabled:
        return
    configured = settings.api_token.get_secret_value() if settings.api_token else None
    if not configured:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Authentication is enabled but no API token is configured")
    if authorization != f"Bearer {configured}":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API token")
