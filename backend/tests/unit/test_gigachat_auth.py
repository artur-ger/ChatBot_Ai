from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.services.gigachat_auth import (
    GigaChatAuthConfig,
    GigaChatTokenManager,
    build_auth_config_from_settings,
    get_gigachat_token_manager,
    reset_gigachat_managers_for_tests,
)
from app.services.llm_client import GigaChatLlmClient, build_llm_client


@pytest.fixture(autouse=True)
def _reset_gigachat_state():
    reset_gigachat_managers_for_tests()
    yield
    reset_gigachat_managers_for_tests()


def _oauth_response(
    *,
    access_token: str = "token-abc",
    expires_at_ms: float = 0,
    expires_in: float = 1800,
) -> httpx.Response:
    body: dict[str, object] = {"access_token": access_token, "expires_in": expires_in}
    if expires_at_ms:
        body["expires_at"] = expires_at_ms
    return httpx.Response(200, json=body)


def _chat_response(content: str = "pong") -> httpx.Response:
    return httpx.Response(
        200,
        json={"choices": [{"message": {"content": content}}]},
    )


@pytest.mark.asyncio
async def test_token_cached_until_refresh_margin():
    config = GigaChatAuthConfig(
        auth_url="https://auth.example/oauth",
        scope="GIGACHAT_API_PERS",
        authorization_key="Basic test-key",
        client_id=None,
        client_secret=None,
        allow_unsafe_tls=True,
        refresh_margin_sec=300,
    )
    manager = GigaChatTokenManager(config)
    expires_at_ms = (time.time() + 1800) * 1000

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = _oauth_response(expires_at_ms=expires_at_ms)
        token1 = await manager.get_token()
        token2 = await manager.get_token()

    assert token1 == "token-abc"
    assert token2 == "token-abc"
    assert mock_post.await_count == 1


@pytest.mark.asyncio
async def test_token_refreshed_when_inside_margin():
    config = GigaChatAuthConfig(
        auth_url="https://auth.example/oauth",
        scope="GIGACHAT_API_PERS",
        authorization_key="Basic test-key",
        client_id=None,
        client_secret=None,
        allow_unsafe_tls=True,
        refresh_margin_sec=300,
    )
    manager = GigaChatTokenManager(config)
    near_expiry_ms = (time.time() + 120) * 1000

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.side_effect = [
            _oauth_response(access_token="token-old", expires_at_ms=near_expiry_ms),
            _oauth_response(access_token="token-new", expires_at_ms=(time.time() + 1800) * 1000),
        ]
        first = await manager.get_token()
        second = await manager.get_token()

    assert first == "token-old"
    assert second == "token-new"
    assert mock_post.await_count == 2


@pytest.mark.asyncio
async def test_force_refresh_bypasses_cache():
    config = GigaChatAuthConfig(
        auth_url="https://auth.example/oauth",
        scope="GIGACHAT_API_PERS",
        authorization_key="Basic test-key",
        client_id=None,
        client_secret=None,
        allow_unsafe_tls=True,
        refresh_margin_sec=300,
    )
    manager = GigaChatTokenManager(config)
    expires_at_ms = (time.time() + 1800) * 1000

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.side_effect = [
            _oauth_response(access_token="token-1", expires_at_ms=expires_at_ms),
            _oauth_response(access_token="token-2", expires_at_ms=expires_at_ms),
        ]
        await manager.get_token()
        refreshed = await manager.get_token(force=True)

    assert refreshed == "token-2"
    assert mock_post.await_count == 2


@pytest.mark.asyncio
async def test_concurrent_get_token_single_oauth_call():
    config = GigaChatAuthConfig(
        auth_url="https://auth.example/oauth",
        scope="GIGACHAT_API_PERS",
        authorization_key="Basic test-key",
        client_id=None,
        client_secret=None,
        allow_unsafe_tls=True,
        refresh_margin_sec=300,
    )
    manager = GigaChatTokenManager(config)
    expires_at_ms = (time.time() + 1800) * 1000

    async def slow_post(*args, **kwargs):
        await asyncio.sleep(0.05)
        return _oauth_response(expires_at_ms=expires_at_ms)

    with patch("httpx.AsyncClient.post", new=AsyncMock(side_effect=slow_post)) as mock_post:
        results = await asyncio.gather(
            manager.get_token(),
            manager.get_token(),
            manager.get_token(),
        )

    assert results == ["token-abc", "token-abc", "token-abc"]
    assert mock_post.await_count == 1


@pytest.mark.asyncio
async def test_basic_auth_from_client_credentials():
    config = GigaChatAuthConfig(
        auth_url="https://auth.example/oauth",
        scope="GIGACHAT_API_PERS",
        authorization_key=None,
        client_id="client-id",
        client_secret="client-secret",
        allow_unsafe_tls=True,
        refresh_margin_sec=300,
    )
    manager = GigaChatTokenManager(config)

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = _oauth_response(expires_at_ms=(time.time() + 1800) * 1000)
        await manager.get_token()

    headers = mock_post.await_args.kwargs["headers"]
    assert headers["Authorization"] == "Basic Y2xpZW50LWlkOmNsaWVudC1zZWNyZXQ="
    assert "RqUID" in headers


@pytest.mark.asyncio
async def test_gigachat_llm_client_retries_on_401():
    client = build_llm_client(
        provider="gigachat",
        model="GigaChat",
        base_url="https://gigachat.example/api/v1",
        api_key="Basic integration-key",
    )
    assert isinstance(client, GigaChatLlmClient)

    oauth_calls = 0
    chat_calls = 0

    async def fake_post(self, url, **kwargs):
        nonlocal oauth_calls, chat_calls
        if "oauth" in str(url) or kwargs.get("data"):
            oauth_calls += 1
            return _oauth_response(
                access_token=f"oauth-{oauth_calls}",
                expires_at_ms=(time.time() + 1800) * 1000,
            )
        chat_calls += 1
        auth = kwargs["headers"]["Authorization"]
        if chat_calls == 1:
            assert auth == "Bearer oauth-1"
            return httpx.Response(401, text="unauthorized")
        assert auth == "Bearer oauth-2"
        return _chat_response("pong")

    with patch("httpx.AsyncClient.post", new=fake_post):
        result = await client.generate("ping")

    assert result == "pong"
    assert oauth_calls == 2
    assert chat_calls == 2


@pytest.mark.asyncio
async def test_get_gigachat_token_manager_reuses_instance():
    first = get_gigachat_token_manager(authorization_key="Basic shared-key")
    second = get_gigachat_token_manager(authorization_key="Basic shared-key")
    assert first is second


def test_build_auth_config_uses_integration_key_only():
    config = build_auth_config_from_settings(authorization_key="Basic integration-key")
    assert config.authorization_key == "Basic integration-key"
