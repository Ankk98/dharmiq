from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, SecretStr, computed_field


def _find_repo_root() -> Path:
    """Walk up from this file to find the repo root (contains config/ dir)."""
    if env_root := os.environ.get("DHARMIQ_ROOT"):
        return Path(env_root).resolve()

    current = Path(__file__).resolve().parent
    for parent in [current, *current.parents]:
        if (parent / "config").is_dir() and (parent / "backend").is_dir():
            return parent
    # Fallback: assume backend/ is sibling to config/
    return Path(__file__).resolve().parents[3]


REPO_ROOT = _find_repo_root()


class ServerSettings(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False


class DatabaseSettings(BaseModel):
    host: str = "localhost"
    port: int = 5432
    name: str = "dharmiq"
    user: str = "dharmiq"
    password: SecretStr = Field(default=SecretStr(""))

    @computed_field  # type: ignore[prop-decorator]
    @property
    def async_url(self) -> str:
        pwd = self.password.get_secret_value()
        return f"postgresql+asyncpg://{self.user}:{pwd}@{self.host}:{self.port}/{self.name}"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def sync_url(self) -> str:
        pwd = self.password.get_secret_value()
        return f"postgresql+psycopg://{self.user}:{pwd}@{self.host}:{self.port}/{self.name}"


class RedisSettings(BaseModel):
    url: str = "redis://localhost:6379/0"


class OpenRouterSettings(BaseModel):
    base_url: str = "https://openrouter.ai/api/v1"
    default_model: str = "deepseek/deepseek-v4-pro"
    api_key: SecretStr = Field(default=SecretStr(""))


class EmbeddingsSettings(BaseModel):
    backend: Literal["local", "remote"] = "local"
    local_model_name: str = "sentence-transformers/all-MiniLM-L6-v2"
    remote_model_id: str = "openai/text-embedding-3-small"


class IngestionSettings(BaseModel):
    corpus_dir: str = "data/corpus/india_code/raw"
    batch_size: int = 10
    concurrency: int = 2


class EvalSettings(BaseModel):
    datasets_dir: str = "data/eval/datasets"


class LoggingSettings(BaseModel):
    level: str = "INFO"
    format: Literal["json", "console"] = "json"


class Settings(BaseModel):
    env: str = "dev"
    repo_root: Path = REPO_ROOT
    server: ServerSettings = Field(default_factory=ServerSettings)
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    redis: RedisSettings = Field(default_factory=RedisSettings)
    openrouter: OpenRouterSettings = Field(default_factory=OpenRouterSettings)
    embeddings: EmbeddingsSettings = Field(default_factory=EmbeddingsSettings)
    ingestion: IngestionSettings = Field(default_factory=IngestionSettings)
    eval: EvalSettings = Field(default_factory=EvalSettings)
    logging: LoggingSettings = Field(default_factory=LoggingSettings)


def _load_yaml_config(env: str) -> dict:
    config_path = REPO_ROOT / "config" / f"config.{env}.yaml"
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")
    with config_path.open() as f:
        return yaml.safe_load(f) or {}


def _apply_env_overrides(settings_dict: dict) -> dict:
    """Overlay secrets and overrides from environment variables."""
    db = settings_dict.setdefault("database", {})
    if password := os.environ.get("DHARMIQ_DATABASE_PASSWORD"):
        db["password"] = password

    openrouter = settings_dict.setdefault("openrouter", {})
    if api_key := os.environ.get("OPENROUTER_API_KEY"):
        openrouter["api_key"] = api_key

    return settings_dict


def load_settings(env: str | None = None) -> Settings:
    resolved_env = env or os.environ.get("DHARMIQ_ENV", "dev")
    raw = _load_yaml_config(resolved_env)
    raw = _apply_env_overrides(raw)
    return Settings(env=resolved_env, **raw)


@lru_cache
def get_settings() -> Settings:
    return load_settings()
