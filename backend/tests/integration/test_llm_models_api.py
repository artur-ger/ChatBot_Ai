from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_lookup_gigachat_models(client):
    with patch(
        "app.api.llm_integrations.list_provider_models",
        new=AsyncMock(return_value=["GigaChat", "GigaChat-2-Pro"]),
    ):
        response = client.post(
            "/api/v1/admin/llm/models/lookup",
            json={
                "provider": "gigachat",
                "api_key": "Basic test-key",
            },
        )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["models"] == ["GigaChat", "GigaChat-2-Pro"]


@pytest.mark.asyncio
async def test_integration_models_uses_stored_key(client):
    create_response = client.post(
        "/api/v1/admin/llm/integrations",
        json={
            "name": "GigaChat",
            "provider": "gigachat",
            "model": "GigaChat",
            "api_key": "Basic test-integration-key",
            "activate": True,
        },
    )
    integration_id = create_response.json()["id"]

    with patch(
        "app.api.llm_integrations.list_provider_models",
        new=AsyncMock(return_value=["GigaChat"]),
    ) as mock_list:
        response = client.post(f"/api/v1/admin/llm/integrations/{integration_id}/models")

    assert response.status_code == 200
    mock_list.assert_awaited_once()
    assert mock_list.await_args.kwargs["api_key"] == "Basic test-integration-key"
