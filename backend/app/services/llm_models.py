from __future__ import annotations

import httpx

from app.core.config import settings
from app.core.errors import DependencyAppError, ValidationAppError
from app.services.gigachat_auth import get_gigachat_token_manager
from app.services.llm_provider_registry import (
    _rule_based_models,
    get_provider_spec,
    validate_models_lookup_credentials,
)


def _parse_models_payload(payload: object) -> list[str]:
    if not isinstance(payload, dict):
        raise DependencyAppError("LLM models response is not a JSON object")

    items: list[object]
    if isinstance(payload.get("data"), list):
        items = payload["data"]
    elif isinstance(payload.get("models"), list):
        items = payload["models"]
    else:
        raise DependencyAppError("LLM models response has no data array")

    models: list[str] = []
    for item in items:
        if isinstance(item, str) and item.strip():
            models.append(item.strip())
            continue
        if isinstance(item, dict):
            model_id = item.get("id") or item.get("name")
            if isinstance(model_id, str) and model_id.strip():
                models.append(model_id.strip())
    if not models:
        raise DependencyAppError("LLM models response is empty")
    return sorted(set(models))


async def list_openai_compatible_models(*, base_url: str, api_key: str | None) -> list[str]:
    normalized = base_url.rstrip("/")
    if normalized.endswith("/v1"):
        endpoint = f"{normalized}/models"
    else:
        endpoint = f"{normalized}/v1/models"

    headers: dict[str, str] = {"Accept": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    try:
        async with httpx.AsyncClient(timeout=settings.llm_timeout_seconds) as client:
            response = await client.get(endpoint, headers=headers)
    except httpx.TimeoutException as exc:
        raise DependencyAppError("LLM models request timed out") from exc
    except httpx.HTTPError as exc:
        raise DependencyAppError(f"LLM models HTTP error: {exc}") from exc

    if response.status_code >= 400:
        detail = response.text[:300]
        raise DependencyAppError(f"LLM models request failed: HTTP {response.status_code} {detail}")

    return _parse_models_payload(response.json())


async def list_gigachat_models(
    *,
    authorization_key: str,
    base_url: str | None = None,
) -> list[str]:
    token = await get_gigachat_token_manager(authorization_key=authorization_key).get_token()
    normalized = (base_url or settings.gigachat_api_url).rstrip("/")
    endpoint = f"{normalized}/models"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    }
    verify_tls = not settings.gigachat_allow_unsafe_tls
    try:
        async with httpx.AsyncClient(verify=verify_tls, timeout=settings.llm_timeout_seconds) as client:
            response = await client.get(endpoint, headers=headers)
    except httpx.TimeoutException as exc:
        raise DependencyAppError("GigaChat models request timed out") from exc
    except httpx.HTTPError as exc:
        raise DependencyAppError(f"GigaChat models HTTP error: {exc}") from exc

    if response.status_code >= 400:
        detail = response.text[:300]
        raise DependencyAppError(
            f"GigaChat models request failed: HTTP {response.status_code} {detail}"
        )

    return _parse_models_payload(response.json())


async def list_provider_models(
    *,
    provider: str,
    api_key: str | None,
    base_url: str | None,
) -> list[str]:
    spec = get_provider_spec(provider)
    if spec.models_source == "static":
        return _rule_based_models()

    validate_models_lookup_credentials(provider=provider, api_key=api_key, base_url=base_url)

    if provider == "openai_compatible":
        assert base_url is not None
        return await list_openai_compatible_models(base_url=base_url, api_key=api_key)
    if provider == "gigachat":
        assert api_key is not None
        return await list_gigachat_models(authorization_key=api_key, base_url=base_url)

    raise ValidationAppError(f"Unsupported provider: {provider}")
