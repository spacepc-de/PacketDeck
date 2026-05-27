from functools import lru_cache

from pydantic import AnyUrl, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=("../.env", ".env"), env_file_encoding="utf-8", extra="ignore")

    app_name: str = "PacketDeck"
    api_prefix: str = "/api/v1"
    database_url: str = "postgresql+asyncpg://meshcore:meshcore@postgres:5432/meshcore"
    mqtt_url: str = "mqtt://mqtt:1883"
    mqtt_topic_prefix: str = "meshcore-webgui"
    meshcore_connection_type: str = "tcp"
    meshcore_tcp_host: str = "127.0.0.1"
    meshcore_tcp_port: int = 5000
    meshcore_auto_reconnect: bool = True
    meshcore_message_max_chars: int = Field(default=180, ge=1, le=4096)
    cors_origins: str = "http://localhost:8080"
    auth_enabled: bool = False
    api_token: SecretStr | None = None
    openai_api_key: SecretStr | None = None
    openai_model: str = "gpt-4.1-mini"

    @field_validator("database_url")
    @classmethod
    def reject_sqlite_primary_database(cls, value: str) -> str:
        if value.startswith("sqlite"):
            raise ValueError("SQLite is only allowed for tests or fixtures, not primary runtime config")
        return value

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
