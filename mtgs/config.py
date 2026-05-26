"""
Application configuration via Pydantic Settings.

All values are read from environment variables (or .env file).
Settings is a singleton — import `settings` everywhere, never instantiate directly.
"""

from __future__ import annotations

from enum import StrEnum
from functools import lru_cache
from typing import Any

from pydantic import AnyHttpUrl, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(StrEnum):
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"
    TEST = "test"


class LogLevel(StrEnum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class ConflictSeverity(StrEnum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INFO = "INFO"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Application ──────────────────────────────────────────────────────────
    app_env: Environment = Environment.DEVELOPMENT
    app_secret_key: str = Field(min_length=16)
    app_debug: bool = False
    app_log_level: LogLevel = LogLevel.INFO
    app_name: str = "MTGS"
    app_version: str = "1.0.0"

    # ── Database ─────────────────────────────────────────────────────────────
    database_url: str = Field(
        description="Async PostgreSQL DSN: postgresql+asyncpg://user:pass@host:port/db"
    )
    database_pool_size: int = 10
    database_max_overflow: int = 20
    database_pool_timeout: int = 30
    database_echo: bool = False  # set True only in dev to log SQL

    # ── Redis ─────────────────────────────────────────────────────────────────
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"

    # ── Azure OpenAI ──────────────────────────────────────────────────────────
    azure_openai_api_key: str = Field(description="Azure OpenAI API key")
    azure_openai_endpoint: str = Field(description="Azure OpenAI resource endpoint")
    azure_openai_api_version: str = "2024-08-01-preview"
    azure_openai_embedding_deployment: str = "text-embedding-3-large"
    azure_openai_chat_deployment: str = "gpt-4o"
    azure_openai_embedding_dimensions: int = 3072  # text-embedding-3-large max

    # ── Azure AI Search ───────────────────────────────────────────────────────
    azure_search_endpoint: str = Field(description="Azure AI Search service endpoint")
    azure_search_api_key: str = Field(description="Azure AI Search admin key")
    azure_search_index_name: str = "mtgs-tool-embeddings"
    azure_search_vector_field: str = "embedding"
    azure_search_top_k: int = 20  # ANN neighbours to retrieve

    # ── Azure Key Vault (optional) ────────────────────────────────────────────
    azure_key_vault_url: str | None = None
    azure_client_id: str | None = None
    azure_client_secret: str | None = None
    azure_tenant_id: str | None = None

    # ── JWT Auth ──────────────────────────────────────────────────────────────
    jwt_secret_key: str = Field(min_length=32)
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 60
    jwt_refresh_token_expire_days: int = 7

    # ── Notifications ─────────────────────────────────────────────────────────
    slack_webhook_url: str | None = None
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: str | None = None
    smtp_from: str = "mtgs@yourdomain.com"

    # ── Observability ─────────────────────────────────────────────────────────
    otel_exporter_otlp_endpoint: str | None = None
    otel_service_name: str = "mtgs-api"

    # ── Governance Defaults ───────────────────────────────────────────────────
    default_semantic_similarity_threshold: float = Field(default=0.80, ge=0.0, le=1.0)
    default_routing_ambiguity_threshold: float = Field(default=0.30, ge=0.0, le=1.0)
    default_probe_query_count: int = Field(default=50, ge=1, le=500)
    default_simulation_trials: int = Field(default=3, ge=1, le=10)
    ci_fail_on_severity: ConflictSeverity = ConflictSeverity.HIGH
    simulation_llm_temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    embedding_cache_ttl_seconds: int = 86400  # 24h

    # ── Rate Limiting ─────────────────────────────────────────────────────────
    rate_limit_per_minute: int = 60
    ci_webhook_rate_limit_per_minute: int = 100

    # ─────────────────────────────────────────────────────────────────────────
    # Derived / Computed
    # ─────────────────────────────────────────────────────────────────────────

    @field_validator("azure_openai_endpoint", "azure_search_endpoint")
    @classmethod
    def strip_trailing_slash(cls, v: str) -> str:
        return v.rstrip("/")

    @model_validator(mode="after")
    def validate_production_settings(self) -> "Settings":
        if self.app_env == Environment.PRODUCTION:
            if self.app_debug:
                raise ValueError("DEBUG must be False in production")
            if "change-me" in self.app_secret_key:
                raise ValueError("APP_SECRET_KEY must be changed in production")
            if "change-me" in self.jwt_secret_key:
                raise ValueError("JWT_SECRET_KEY must be changed in production")
        return self

    @property
    def is_production(self) -> bool:
        return self.app_env == Environment.PRODUCTION

    @property
    def is_test(self) -> bool:
        return self.app_env == Environment.TEST

    @property
    def sync_database_url(self) -> str:
        """Synchronous DSN used by Alembic migrations."""
        return self.database_url.replace("postgresql+asyncpg://", "postgresql+psycopg2://")

    def model_dump_safe(self) -> dict[str, Any]:
        """Dump settings with sensitive fields redacted — safe to log."""
        data = self.model_dump()
        sensitive = {
            "app_secret_key",
            "jwt_secret_key",
            "azure_openai_api_key",
            "azure_search_api_key",
            "azure_client_secret",
            "smtp_password",
        }
        return {k: "***REDACTED***" if k in sensitive else v for k, v in data.items()}


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the cached Settings singleton."""
    return Settings()  # type: ignore[call-arg]


# Module-level singleton — import this everywhere
settings = get_settings()
