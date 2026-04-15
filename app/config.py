from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8', extra='ignore')

    BOT_TOKEN: str = Field(default='', min_length=0)
    ENV: str = 'staging'
    LOG_LEVEL: str = 'INFO'
    STORAGE_BACKEND: str = 'memory'
    SPREADSHEET_ID: str = ''
    SUPERADMIN_TG_ID: int = 0
    BASE_URL: str = ''
    WEBHOOK_SECRET: str | None = None
    PORT: int = 8080
    VERSION: str = '2.0-fixed'
    LOW_STOCK_NOTIFY_CHAT_ID: int | None = None
    LOW_STOCK_THROTTLE_MINUTES: int = 120


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
