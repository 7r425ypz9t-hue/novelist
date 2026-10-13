"""Runtime configuration. All secrets come from the server environment, never from the client."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="NIS_", env_file=".env", extra="ignore")

    # Storage
    database_url: str = "sqlite:///./var/nis.db"
    data_dir: Path = Path("./var/data")

    # HTTP
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]
    serve_spa: bool = True
    rate_limit_per_minute: int = 600
    auth_rate_limit_per_minute: int = 20
    max_upload_mb: int = 25

    # Auth
    session_days: int = 14
    first_user_is_admin: bool = True
    allow_registration: bool = True

    # Agents / models. Default is fully disabled: the studio works without any model.
    llm_provider: str = "disabled"  # disabled | anthropic | openai_compatible
    llm_model: str = ""
    llm_base_url: str = ""  # for openai_compatible (e.g. a local Ollama / LM Studio endpoint)
    llm_api_key: str = ""  # read from env only; never returned by the API
    llm_timeout_s: float = 90.0
    run_max_steps: int = 24
    run_token_budget: int = 60_000
    runs_inline: bool = False  # execute agent runs synchronously (tests / single-process mode)

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")


@lru_cache
def get_settings() -> Settings:
    return Settings()
