from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from httpx import Response

from app.services.llm_client import RuleBasedLlmClient


@pytest.mark.asyncio
async def test_llm_integrations_crud_and_activate(client):
    create_response = client.post(
        "/api/v1/admin/llm/integrations",
        json={
            "name": "Primary OpenAI",
            "provider": "openai_compatible",
            "model": "gpt-4o-mini",
            "base_url": "https://api.openai.com/v1",
            "api_key": "sk-test-key-12345678",
            "enabled": True,
            "activate": True,
        },
    )
    assert create_response.status_code == 201, create_response.text
    created = create_response.json()
    integration_id = created["id"]
    assert created["is_active"] is True
    assert created["api_key_masked"] is not None
    assert "sk-t" in created["api_key_masked"]

    list_response = client.get("/api/v1/admin/llm/integrations")
    assert list_response.status_code == 200
    listed = list_response.json()
    assert listed["active_integration_id"] == integration_id
    assert len(listed["items"]) == 1

    second = client.post(
        "/api/v1/admin/llm/integrations",
        json={
            "name": "Backup rule",
            "provider": "rule_based",
            "model": "rule-based",
            "enabled": True,
            "activate": False,
        },
    )
    assert second.status_code == 201
    second_id = second.json()["id"]

    activate_response = client.post(f"/api/v1/admin/llm/integrations/{second_id}/activate")
    assert activate_response.status_code == 200
    assert activate_response.json()["is_active"] is True

    get_first = client.get(f"/api/v1/admin/llm/integrations/{integration_id}")
    assert get_first.status_code == 200
    assert get_first.json()["is_active"] is False

    delete_response = client.delete(f"/api/v1/admin/llm/integrations/{integration_id}")
    assert delete_response.status_code == 200

    info_response = client.get("/system/info")
    assert info_response.status_code == 200
    info = info_response.json()
    assert info["llm_integrations_count"] == 1
    assert info["active_llm_integration_id"] == second_id


@pytest.mark.asyncio
async def test_llm_integration_test_endpoint(client):
    create_response = client.post(
        "/api/v1/admin/llm/integrations",
        json={
            "name": "Rule test",
            "provider": "rule_based",
            "model": "rule-based",
            "activate": True,
        },
    )
    integration_id = create_response.json()["id"]

    with patch.object(RuleBasedLlmClient, "generate", new=AsyncMock(return_value="pong")):
        test_response = client.post(f"/api/v1/admin/llm/integrations/{integration_id}/test")

    assert test_response.status_code == 200
    payload = test_response.json()
    assert payload["ok"] is True
    assert payload["integration_id"] == integration_id


@pytest.mark.asyncio
async def test_openai_compatible_test_uses_http(client):
    create_response = client.post(
        "/api/v1/admin/llm/integrations",
        json={
            "name": "OpenAI",
            "provider": "openai_compatible",
            "model": "gpt-4o-mini",
            "base_url": "https://api.openai.com/v1",
            "api_key": "sk-test-key-12345678",
            "activate": True,
        },
    )
    integration_id = create_response.json()["id"]

    async def fake_post(self, url, headers=None, json=None):
        return Response(
            200,
            json={"choices": [{"message": {"content": "pong"}}]},
        )

    with patch("httpx.AsyncClient.post", new=fake_post):
        test_response = client.post(f"/api/v1/admin/llm/integrations/{integration_id}/test")

    assert test_response.status_code == 200
    assert test_response.json()["ok"] is True
