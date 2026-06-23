from __future__ import annotations

import os
import uuid
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


def _load_dotenv() -> None:
    """Load repo-root `.env` so CLI tools (alembic, celery) pick up secrets."""
    from dotenv import load_dotenv

    env_file = REPO_ROOT / ".env"
    if env_file.exists():
        load_dotenv(env_file, override=False)


_load_dotenv()


class ServerSettings(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])


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


class AgentGraphSettings(BaseModel):
    enabled: bool = True
    debug_progress: bool = False


class LLMRoleSettings(BaseModel):
    primary: str = "openrouter/deepseek/deepseek-v4-pro"
    fast: str = "openrouter/deepseek/deepseek-v4-flash"
    embedding: Literal["local"] = "local"


class LLMAgentReasoningSettings(BaseModel):
    enabled: bool = False


class LLMAgentSettings(BaseModel):
    model: str | None = None
    reasoning: LLMAgentReasoningSettings = Field(default_factory=LLMAgentReasoningSettings)


class LLMAgentsSettings(BaseModel):
    validator: LLMAgentSettings = Field(default_factory=LLMAgentSettings)


class LLMRerankSettings(BaseModel):
    backend: Literal["local", "litellm"] = "local"
    local_model: str = "BAAI/bge-reranker-base"
    litellm_model: str = "cohere/rerank-english-v3.0"
    api_key_env: str = "COHERE_API_KEY"


class LLMSettings(BaseModel):
    roles: LLMRoleSettings = Field(default_factory=LLMRoleSettings)
    agents: LLMAgentsSettings = Field(default_factory=LLMAgentsSettings)
    rerank: LLMRerankSettings = Field(default_factory=LLMRerankSettings)


class OpenRouterSettings(BaseModel):
    base_url: str = "https://openrouter.ai/api/v1"
    default_model: str = "deepseek/deepseek-v4-pro"
    api_key: SecretStr = Field(default=SecretStr(""))
    timeout_seconds: float = 60.0
    max_retries: int = 3


class EmbeddingsSettings(BaseModel):
    backend: Literal["local", "remote"] = "local"
    local_model_name: str = "sentence-transformers/all-MiniLM-L6-v2"
    local_dimensions: int = 384
    remote_model_id: str = "openai/text-embedding-3-small"
    remote_dimensions: int = 1536

    @property
    def dimensions(self) -> int:
        return self.remote_dimensions if self.backend == "remote" else self.local_dimensions


class RetrievalSettings(BaseModel):
    top_k: int = 5
    multi_query_top_k: int = 5
    vector_top_k: int = 30
    bm25_top_k: int = 30
    rrf_k: int = 60
    rrf_top_k: int = 20
    rerank_top_k: int = 8
    min_rerank_score: float = 0.35
    min_relevant_chunks: int = 2
    include_superseded: bool = False


class ChatSettings(BaseModel):
    history_limit: int = 20
    max_validator_retries: int = 3
    slow_threshold_seconds: float = 30.0
    server_timeout_seconds: float = 60.0


class GuardrailsSettings(BaseModel):
    max_message_length: int = 8192
    requests_per_minute: int = 10
    requests_per_day: int = 200


class IngestionSettings(BaseModel):
    corpus_dir: str = "data/corpus/india_code/raw"
    batch_size: int = 10
    concurrency: int = 2
    min_page_text_chars: int = 50
    chunk_min_chars: int = 2000
    chunk_max_chars: int = 4000
    chunk_overlap_chars: int = 200
    child_chunk_target_tokens: int = 300
    parent_max_tokens: int = 2048
    overlap_tokens: int = 64
    context_text_max_tokens: int = 512
    preserve_section_atomic: bool = True
    ocr_languages: str = "eng"

    def resolve_corpus_dir(self, repo_root: Path) -> Path:
        path = Path(self.corpus_dir)
        if path.is_absolute():
            return path
        return (repo_root / path).resolve()


class CorpusSettings(BaseModel):
    default_allowlist_path: str = "docs/plans/v0.6/central-corpus-allowlist.yaml"
    max_chunk_count: int = 250_000

    def resolve_allowlist_path(self, repo_root: Path) -> Path:
        path = Path(self.default_allowlist_path)
        if path.is_absolute():
            return path
        return (repo_root / path).resolve()


class UploadSettings(BaseModel):
    uploads_dir: str = "data/uploads"
    max_assets_per_user: int = 30
    max_size_bytes: int = 100 * 1024 * 1024

    def resolve_uploads_dir(self, repo_root: Path) -> Path:
        path = Path(self.uploads_dir)
        if path.is_absolute():
            return path
        return (repo_root / path).resolve()

    def user_raw_dir(self, repo_root: Path, user_id: uuid.UUID) -> Path:
        return self.resolve_uploads_dir(repo_root) / str(user_id) / "raw"


class EvalSettings(BaseModel):
    datasets_dir: str = "data/eval/datasets"
    runs_dir: str = "data/eval/runs"

    def resolve_datasets_dir(self, repo_root: Path) -> Path:
        path = Path(self.datasets_dir)
        if path.is_absolute():
            return path
        return (repo_root / path).resolve()

    def resolve_runs_dir(self, repo_root: Path) -> Path:
        path = Path(self.runs_dir)
        if path.is_absolute():
            return path
        return (repo_root / path).resolve()


class LoggingSettings(BaseModel):
    level: str = "INFO"
    format: Literal["json", "console"] = "json"


class AuthSettings(BaseModel):
    jwt_secret: SecretStr = Field(default=SecretStr(""))
    jwt_lifetime_seconds: int = 3600


class CostLimitsSettings(BaseModel):
    enforce: bool = True
    per_session_usd: float = 1.0
    per_account_monthly_usd: float = 10.0


class BeatScheduleSettings(BaseModel):
    enabled: bool = True


class Settings(BaseModel):
    env: str = "dev"
    repo_root: Path = REPO_ROOT
    server: ServerSettings = Field(default_factory=ServerSettings)
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    redis: RedisSettings = Field(default_factory=RedisSettings)
    agent_graph: AgentGraphSettings = Field(default_factory=AgentGraphSettings)
    llm: LLMSettings = Field(default_factory=LLMSettings)
    openrouter: OpenRouterSettings = Field(default_factory=OpenRouterSettings)
    embeddings: EmbeddingsSettings = Field(default_factory=EmbeddingsSettings)
    retrieval: RetrievalSettings = Field(default_factory=RetrievalSettings)
    chat: ChatSettings = Field(default_factory=ChatSettings)
    guardrails: GuardrailsSettings = Field(default_factory=GuardrailsSettings)
    ingestion: IngestionSettings = Field(default_factory=IngestionSettings)
    corpus: CorpusSettings = Field(default_factory=CorpusSettings)
    uploads: UploadSettings = Field(default_factory=UploadSettings)
    eval: EvalSettings = Field(default_factory=EvalSettings)
    logging: LoggingSettings = Field(default_factory=LoggingSettings)
    auth: AuthSettings = Field(default_factory=AuthSettings)
    cost_limits: CostLimitsSettings = Field(default_factory=CostLimitsSettings)
    beat_schedule: BeatScheduleSettings = Field(default_factory=BeatScheduleSettings)


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

    auth = settings_dict.setdefault("auth", {})
    if jwt_secret := os.environ.get("DHARMIQ_JWT_SECRET"):
        auth["jwt_secret"] = jwt_secret

    agent_graph = settings_dict.setdefault("agent_graph", {})
    if flag := os.environ.get("DHARMIQ_AGENT_GRAPH_V2"):
        agent_graph["enabled"] = flag.lower() in {"1", "true", "yes"}
    if (debug_flag := os.environ.get("DHARMIQ_DEBUG_PROGRESS")) and debug_flag.lower() in {
        "1",
        "true",
        "yes",
    }:
        agent_graph["debug_progress"] = True

    if flag := os.environ.get("DHARMIQ_COST_LIMITS_ENFORCE"):
        settings_dict.setdefault("cost_limits", {})["enforce"] = flag.lower() not in {
            "0",
            "false",
            "no",
        }

    return settings_dict


def load_settings(env: str | None = None) -> Settings:
    resolved_env = env or os.environ.get("DHARMIQ_ENV", "dev")
    raw = _load_yaml_config(resolved_env)
    raw = _apply_env_overrides(raw)
    raw["repo_root"] = _find_repo_root()
    return Settings(env=resolved_env, **raw)


@lru_cache
def get_settings() -> Settings:
    return load_settings()
