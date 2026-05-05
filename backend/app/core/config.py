from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    app_name: str = "ChatBot AI Backend"
    api_prefix: str = "/api/v1"
    database_url: str = Field(
        default="postgresql+asyncpg://chatbot:chatbot@localhost:5432/chatbot_ai"
    )

    upload_temp_dir: str = Field(default="./data/uploads")
    max_upload_bytes: int = Field(default=10 * 1024 * 1024)
    allowed_mime_types: tuple[str, ...] = Field(
        default=(
            "text/plain",
            "text/markdown",
            "application/pdf",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
    )

    celery_broker_url: str = Field(default="redis://localhost:6379/0")
    celery_result_backend: str = Field(default="redis://localhost:6379/1")

    chroma_host: str | None = Field(default="localhost")
    chroma_port: int = Field(default=8001)
    chroma_persist_path: str = Field(default="./data/chroma")

    embedding_model_name: str = Field(default="sentence-transformers/all-MiniLM-L6-v2")
    embedding_model_version: str = Field(default="all-MiniLM-L6-v2")
    use_fake_embeddings: bool = Field(default=False)

    chunk_size: int = Field(default=900)
    chunk_overlap: int = Field(default=120)

    retriever_top_k: int = 5
    min_chunk_score: float = 0.25
    llm_timeout_seconds: float = 6.0
    llm_retry_attempts: int = 2
    llm_model: str = Field(default="rule-based-llm")

    chat_history_max_messages: int = Field(default=12)
    chat_history_max_chars: int = Field(default=6000)
    chat_acl_secret: str = Field(default="local-dev-chat-secret")
    # When True, X-Chat-Signature is not required (local/dev only; set False in production).
    chat_acl_disabled: bool = Field(default=False)

    rate_limit_default: str = Field(default="60/minute")
    rate_limit_chat: str = Field(default="30/minute")

    otel_exporter_otlp_endpoint: str | None = Field(default=None)
    alert_webhook_url: str | None = Field(default=None)

    reindex_batch_size: int = Field(default=25)
    llm_circuit_breaker_threshold: int = Field(default=3)
    llm_circuit_breaker_cooldown_sec: int = Field(default=30)
    chat_cache_ttl_sec: int = Field(default=45)
    chat_cache_max_items: int = Field(default=200)


settings = Settings()
