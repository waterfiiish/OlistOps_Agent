from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Runtime settings loaded from the project-local .env file."""

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_env: Literal["development", "test", "production"] = "development"
    app_secret_key: str = "replace-me-before-sharing"
    api_host: str = "127.0.0.1"
    api_port: int = 8000
    web_origin: str = "http://127.0.0.1:5173"
    database_url: str = (
        "postgresql+psycopg://olistops:olistops@127.0.0.1:55432/olistops"
    )
    workspace_root: Path = PROJECT_ROOT / "workspace"

    model_default_profile: str = "local_lite"
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen2.5:3b"
    cloud_api_base: str = ""
    cloud_api_key: str = ""
    cloud_model_name: str = ""

    embedding_provider: str = "local"
    embedding_model: str = ""
    embedding_dimensions: int = Field(default=384, ge=32, le=4096)
    retrieval_mode: Literal["hybrid", "fts", "vector"] = "hybrid"
    retrieval_candidate_k: int = Field(default=30, ge=5, le=200)
    retrieval_rrf_k: int = Field(default=60, ge=1, le=500)
    retrieval_fts_weight: float = Field(default=0.75, ge=0, le=1)
    retrieval_vector_weight: float = Field(default=0.25, ge=0, le=1)
    reranker_enabled: bool = False

    max_agent_steps: int = Field(default=10, ge=1, le=50)
    max_tool_calls: int = Field(default=8, ge=1, le=30)
    max_run_seconds: int = Field(default=120, ge=5, le=1800)
    max_result_rows: int = Field(default=500, ge=1, le=5000)
    max_upload_mb: int = Field(default=20, ge=1, le=200)
    trace_content_mode: Literal["redacted", "full", "disabled"] = "redacted"

    @property
    def psycopg_url(self) -> str:
        return self.database_url.replace("postgresql+psycopg://", "postgresql://", 1)

    def ensure_local_paths(self) -> None:
        workspace = self.workspace_root
        if not workspace.is_absolute():
            workspace = (PROJECT_ROOT / workspace).resolve()
            self.workspace_root = workspace
        workspace.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_local_paths()
    return settings
