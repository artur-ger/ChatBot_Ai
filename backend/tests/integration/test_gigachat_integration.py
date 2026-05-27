from __future__ import annotations



from unittest.mock import AsyncMock, patch



import pytest





@pytest.mark.asyncio

async def test_gigachat_integration_crud(client):

    create_response = client.post(

        "/api/v1/admin/llm/integrations",

        json={

            "name": "GigaChat prod",

            "provider": "gigachat",

            "model": "GigaChat",

            "api_key": "Basic test-integration-key",

            "enabled": True,

            "activate": True,

        },

    )

    assert create_response.status_code == 201, create_response.text

    created = create_response.json()

    assert created["provider"] == "gigachat"

    assert created["is_active"] is True





@pytest.mark.asyncio

async def test_gigachat_integration_requires_api_key(client):

    response = client.post(

        "/api/v1/admin/llm/integrations",

        json={

            "name": "GigaChat",

            "provider": "gigachat",

            "model": "GigaChat",

            "activate": True,

        },

    )

    assert response.status_code == 400





@pytest.mark.asyncio

async def test_gigachat_integration_test_endpoint(client):

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



    mock_client = AsyncMock()

    mock_client.generate = AsyncMock(return_value="pong")

    with patch("app.services.llm_integration_service.build_llm_client", return_value=mock_client):

        test_response = client.post(f"/api/v1/admin/llm/integrations/{integration_id}/test")



    assert test_response.status_code == 200

    assert test_response.json()["ok"] is True

