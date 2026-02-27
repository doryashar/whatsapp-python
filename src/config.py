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

    max_messages: int = Field(default=1000, alias="MAX_MESSAGES")
    auto_login: bool = Field(default=False, alias="AUTO_LOGIN")

    webhook_urls: list[str] = Field(default_factory=list, alias="WEBHOOK_URLS")
    webhook_secret: str = Field(default="", alias="WEBHOOK_SECRET")
    webhook_timeout: int = Field(default=30, alias="WEBHOOK_TIMEOUT")
    webhook_retries: int = Field(default=3, alias="WEBHOOK_RETRIES")

    model_config = {"env_prefix": "", "populate_by_name": True}


settings = Settings()
