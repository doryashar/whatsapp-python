from pydantic_settings import BaseSettings
from pydantic import Field
from pathlib import Path


class Settings(BaseSettings):
    host: str = Field(default="0.0.0.0", alias="HOST")
    port: int = Field(default=8080, alias="PORT")
    debug: bool = Field(default=False, alias="DEBUG")

    bridge_path: Path = Field(
        default=Path(__file__).parent.parent.parent / "bridge" / "index.mjs",
        alias="BRIDGE_PATH",
    )
    auth_dir: Path = Field(
        default=Path(__file__).parent.parent.parent / "data" / "auth",
        alias="WHATSAPP_AUTH_DIR",
    )
    data_dir: Path = Field(
        default=Path(__file__).parent.parent.parent / "data",
        alias="DATA_DIR",
    )

    max_messages: int = Field(default=1000, alias="MAX_MESSAGES")
    auto_login: bool = Field(default=True, alias="AUTO_LOGIN")
    webhook_urls: list[str] = Field(default_factory=list, alias="WEBHOOK_URLS")
    webhook_secret: str = Field(default="", alias="WEBHOOK_SECRET")
    webhook_timeout: int = Field(default=30, alias="WEBHOOK_TIMEOUT")
    webhook_retries: int = Field(default=3, alias="WEBHOOK_RETRIES")
    admin_api_key: str = Field(default="", alias="ADMIN_API_KEY")
    admin_password: str = Field(default="", alias="ADMIN_PASSWORD")
    database_url: str = Field(default="", alias="DATABASE_URL")

    otlp_endpoint: str = Field(default="", alias="OTEL_EXPORTER_OTLP_ENDPOINT")
    service_name: str = Field(default="whatsapp-api", alias="OTEL_SERVICE_NAME")
    service_version: str = Field(default="2.0.0", alias="OTEL_SERVICE_VERSION")

    rate_limit_per_minute: int = Field(default=60, alias="RATE_LIMIT_PER_MINUTE")
    rate_limit_per_hour: int = Field(default=1000, alias="RATE_LIMIT_PER_HOUR")
    rate_limit_block_minutes: int = Field(default=15, alias="RATE_LIMIT_BLOCK_MINUTES")
    max_failed_auth_attempts: int = Field(default=5, alias="MAX_FAILED_AUTH_ATTEMPTS")
    failed_auth_window_minutes: int = Field(
        default=15, alias="FAILED_AUTH_WINDOW_MINUTES"
    )

    model_config = {"env_prefix": "", "populate_by_name": True}


settings = Settings()
