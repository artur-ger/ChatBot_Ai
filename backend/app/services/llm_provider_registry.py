from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Literal

from app.core.config import settings
from app.core.errors import ValidationAppError
from app.schemas.llm_integration import LlmProviderType

ModelsFetcher = Callable[..., Awaitable[list[str]]]


@dataclass(frozen=True)
class LlmProviderSpec:
    id: LlmProviderType
    label: str
    requires_base_url: bool
    requires_api_key: bool
    api_key_optional: bool
    base_url_placeholder: str
    api_key_placeholder: str
    models_source: Literal["static", "remote"]
    description: str


def _rule_based_models() -> list[str]:
    return [settings.llm_model]


LLM_PROVIDER_SPECS: dict[LlmProviderType, LlmProviderSpec] = {
    "openai_compatible": LlmProviderSpec(
        id="openai_compatible",
        label="OpenAI-compatible",
        requires_base_url=True,
        requires_api_key=False,
        api_key_optional=True,
        base_url_placeholder="https://api.openai.com/v1 · http://localhost:11434/v1 (Ollama)",
        api_key_placeholder="API key (если требуется провайдером)",
        models_source="remote",
        description="OpenAI API, Ollama, LM Studio, OpenRouter и другие совместимые сервисы",
    ),
    "gigachat": LlmProviderSpec(
        id="gigachat",
        label="GigaChat",
        requires_base_url=False,
        requires_api_key=True,
        api_key_optional=False,
        base_url_placeholder="Можно оставить пустым — используется адрес по умолчанию",
        api_key_placeholder="Authorization Basic ... из кабинета Sber",
        models_source="remote",
        description="GigaChat API (OAuth, токен обновляется автоматически)",
    ),
    "rule_based": LlmProviderSpec(
        id="rule_based",
        label="rule_based (dev)",
        requires_base_url=False,
        requires_api_key=False,
        api_key_optional=True,
        base_url_placeholder="",
        api_key_placeholder="",
        models_source="static",
        description="Локальная заглушка без внешней нейросети",
    ),
}


def get_provider_spec(provider: str) -> LlmProviderSpec:
    spec = LLM_PROVIDER_SPECS.get(provider)  # type: ignore[arg-type]
    if spec is None:
        raise ValidationAppError(f"Unsupported provider: {provider}")
    return spec


def list_provider_specs() -> list[LlmProviderSpec]:
    return list(LLM_PROVIDER_SPECS.values())


def validate_models_lookup_credentials(
    *,
    provider: str,
    api_key: str | None,
    base_url: str | None,
) -> None:
    spec = get_provider_spec(provider)
    if spec.models_source == "static":
        return
    if spec.requires_base_url and not base_url:
        raise ValidationAppError(f"base_url обязателен для провайдера {spec.label}")
    if spec.requires_api_key and not api_key:
        raise ValidationAppError(
            f"api_key обязателен для провайдера {spec.label}. "
            f"{spec.api_key_placeholder}"
        )
