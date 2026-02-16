from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8', extra='ignore')

    BOT_TOKEN: str = Field(min_length=1)
    ENV: str = 'staging'
    LOG_LEVEL: str = 'INFO'
    STORAGE_BACKEND: str = 'memory'
    SPREADSHEET_ID: str = ''
    SUPERADMIN_TG_ID: int = 0
    BASE_URL: str = ''
    WEBHOOK_SECRET: str | None = None
    PORT: int = 8080
    VERSION: str = '2.0-fixed'


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
