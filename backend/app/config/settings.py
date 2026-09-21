from __future__ import annotations

from functools import lru_cache
from typing import Annotated

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "MerchantMind"
    app_env: str = "local"
    app_version: str = "0.1.0"
    api_prefix: str = "/api"

    database_url: str = (
        "postgresql+psycopg://merchantmind:merchantmind@localhost:5432/merchantmind"
    )
    db_connect_timeout_seconds: float = 3.0

    backend_cors_origins: Annotated[list[str], NoDecode] = ["http://localhost:3000"]

    embedding_provider: str = "local"
    embedding_dim: int = 256

    # Knowledge RAG is independently selectable:
    #  embedding provider: local(hash,256) | bge(pretrained,512) | openai(online)
    #  retrieval strategy: vector(pgvector) | bm25(lexical) | hybrid(RRF)
    knowledge_embedding_provider: str = "local"
    knowledge_retrieval_strategy: str = "vector"
    openai_embedding_model: str = "text-embedding-3-small"
    llm_provider: str = "local"
    llm_base_url: str = ""
    llm_api_key: str = ""
    llm_model: str = "local-deterministic"

    memory_top_k: int = 5
    memory_weight_semantic: float = 0.35
    memory_weight_recency: float = 0.25
    memory_weight_importance: float = 0.20
    memory_weight_relevance: float = 0.20
    memory_dedup_threshold: float = 0.88
    memory_candidate_confidence: float = 0.60
    memory_active_confidence: float = 0.75
    memory_expiry_days: int = 180

    knowledge_top_k: int = 5
    quality_retry_threshold: float = 0.70

    # Intent classifier backend: rule | ml | hybrid. "rule" stays default so
    # offline evaluation is reproducible; "ml" uses the trained softmax model
    # (falls back to rule if its weight artifacts are missing).
    intent_classifier_backend: str = "rule"

    @field_validator("backend_cors_origins", mode="before")
    @classmethod
    def _split_cors_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
