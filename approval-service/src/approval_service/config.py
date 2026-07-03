from pydantic import PostgresDsn
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="APPROVAL_")

    database_url: PostgresDsn
    database_pool_size: int = 10
    database_max_overflow: int = 5
    database_echo: bool = False

    idempotency_key_ttl_hours: int = 24

    outbox_poll_interval_seconds: int = 5
    outbox_batch_size: int = 100
    outbox_max_retries: int = 5

    log_level: str = "INFO"
    cors_origins: list[str] = []


def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
