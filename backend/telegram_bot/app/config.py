from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class BotSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    telegram_bot_token: str = Field(alias="TELEGRAM_BOT_TOKEN")
    core_api_base_url: str = Field(default="http://backend:8000/api/v1", alias="CORE_API_BASE_URL")

    request_timeout_seconds: float = Field(default=10.0, alias="BOT_REQUEST_TIMEOUT_SECONDS")
    upload_poll_interval_seconds: float = Field(default=2.0, alias="BOT_UPLOAD_POLL_INTERVAL_SECONDS")
    upload_poll_attempts: int = Field(default=30, alias="BOT_UPLOAD_POLL_ATTEMPTS")

    bot_storage_path: str = Field(default="/app/data/bot.sqlite3", alias="BOT_STORAGE_PATH")

    max_telegram_message_length: int = 4096
    supported_extensions: set[str] = {".pdf", ".docx", ".txt", ".md", ".markdown"}


settings = BotSettings()