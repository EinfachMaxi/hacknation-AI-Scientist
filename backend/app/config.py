from pathlib import Path
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

ENV_PATH = Path(__file__).resolve().parents[1] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ENV_PATH, env_file_encoding="utf-8", extra="ignore")

    supabase_url: str = ""
    supabase_anon_key: str = ""
    supabase_service_key: str = ""
    tavily_api_key: str = ""
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    allowed_origins: str = "http://localhost:5173"
    max_plan_size_mb: int = 5
    streaming_timeout_seconds: int = 120


@lru_cache
def get_settings() -> Settings:
    return Settings()
