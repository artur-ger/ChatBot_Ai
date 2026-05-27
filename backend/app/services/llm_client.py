from __future__ import annotations

import asyncio
import logging

import httpx

from app.core.config import settings
from app.core.errors import DependencyAppError, ValidationAppError
from app.services.gigachat_auth import get_gigachat_token_manager
from app.services.rag_answer_extract import generate_rule_based_answer

logger = logging.getLogger(__name__)


class BaseLlmClient:
    async def generate(self, prompt: str) -> str:
        raise NotImplementedError


class RuleBasedLlmClient(BaseLlmClient):
    async def generate(self, prompt: str) -> str:
        await asyncio.sleep(0)
        return generate_rule_based_answer(prompt)


class OpenAICompatibleLlmClient(BaseLlmClient):
    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        api_key: str,
        timeout_seconds: float | None = None,
    ) -> None:
        normalized = base_url.rstrip("/")
        if normalized.endswith("/v1"):
            self._endpoint = f"{normalized}/chat/completions"
        else:
            self._endpoint = f"{normalized}/v1/chat/completions"
        self._model = model
        self._api_key = api_key
        self._timeout = timeout_seconds or settings.llm_timeout_seconds

    async def generate(self, prompt: str) -> str:
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self._model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2,
        }
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(self._endpoint, headers=headers, json=payload)
        except httpx.TimeoutException as exc:
            raise DependencyAppError("LLM request timed out") from exc
        except httpx.HTTPError as exc:
            raise DependencyAppError(f"LLM HTTP error: {exc}") from exc

        if response.status_code >= 500:
            raise DependencyAppError(f"LLM upstream error: HTTP {response.status_code}")
        if response.status_code >= 400:
            detail = response.text[:300]
            raise DependencyAppError(f"LLM rejected request: HTTP {response.status_code} {detail}")

        data = response.json()
        choices = data.get("choices")
        if not isinstance(choices, list) or not choices:
            raise DependencyAppError("LLM response has no choices")
        message = choices[0].get("message") if isinstance(choices[0], dict) else None
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, str) or not content.strip():
            raise DependencyAppError("LLM response has empty content")
        return content.strip()


class GigaChatLlmClient(BaseLlmClient):
    def __init__(
        self,
        *,
        model: str,
        base_url: str | None = None,
        authorization_key: str | None = None,
        timeout_seconds: float | None = None,
    ) -> None:
        normalized = (base_url or settings.gigachat_api_url).rstrip("/")
        self._endpoint = f"{normalized}/chat/completions"
        self._model = model
        self._timeout = timeout_seconds or settings.llm_timeout_seconds
        self._token_manager = get_gigachat_token_manager(authorization_key=authorization_key)
        self._verify_tls = not settings.gigachat_allow_unsafe_tls

    async def generate(self, prompt: str) -> str:
        token = await self._token_manager.get_token()
        try:
            response = await self._request(token, prompt)
        except DependencyAppError as exc:
            if "HTTP 401" not in str(exc):
                raise
            token = await self._token_manager.get_token(force=True)
            response = await self._request(token, prompt)
        return self._parse_response(response)

    async def _request(self, token: str, prompt: str) -> httpx.Response:
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        payload = {
            "model": self._model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2,
        }
        try:
            async with httpx.AsyncClient(verify=self._verify_tls, timeout=self._timeout) as client:
                response = await client.post(self._endpoint, headers=headers, json=payload)
        except httpx.TimeoutException as exc:
            raise DependencyAppError("LLM request timed out") from exc
        except httpx.HTTPError as exc:
            raise DependencyAppError(f"LLM HTTP error: {exc}") from exc

        if response.status_code >= 500:
            raise DependencyAppError(f"LLM upstream error: HTTP {response.status_code}")
        if response.status_code >= 400:
            detail = response.text[:300]
            raise DependencyAppError(
                f"LLM rejected request: HTTP {response.status_code} {detail}"
            )
        return response

    @staticmethod
    def _parse_response(response: httpx.Response) -> str:
        data = response.json()
        choices = data.get("choices")
        if not isinstance(choices, list) or not choices:
            raise DependencyAppError("LLM response has no choices")
        message = choices[0].get("message") if isinstance(choices[0], dict) else None
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, str) or not content.strip():
            raise DependencyAppError("LLM response has empty content")
        return content.strip()


def build_llm_client(
    *,
    provider: str,
    model: str,
    base_url: str | None,
    api_key: str | None,
) -> BaseLlmClient:
    if provider == "rule_based":
        return RuleBasedLlmClient()
    if provider == "openai_compatible":
        if not base_url:
            raise ValidationAppError("base_url is required for openai_compatible provider")
        if not api_key:
            raise ValidationAppError("api_key is required for openai_compatible provider")
        return OpenAICompatibleLlmClient(base_url=base_url, model=model, api_key=api_key)
    if provider == "gigachat":
        if not api_key:
            raise ValidationAppError(
                "api_key (Basic ...) обязателен для gigachat — настройте в админке LLM integrations"
            )
        return GigaChatLlmClient(
            model=model,
            base_url=base_url,
            authorization_key=api_key,
        )
    raise ValidationAppError(f"Unsupported LLM provider: {provider}")
