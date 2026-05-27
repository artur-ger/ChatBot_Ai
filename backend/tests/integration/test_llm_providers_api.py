import pytest


@pytest.mark.asyncio
async def test_list_llm_providers(client):
    response = client.get("/api/v1/admin/llm/providers")
    assert response.status_code == 200, response.text
    items = response.json()["items"]
    ids = {item["id"] for item in items}
    assert ids == {"openai_compatible", "gigachat", "rule_based"}
    gigachat = next(item for item in items if item["id"] == "gigachat")
    openai = next(item for item in items if item["id"] == "openai_compatible")
    assert gigachat["models_source"] == "remote"
    assert gigachat["requires_api_key"] is True
    assert openai["models_source"] == "remote"
    assert openai["requires_base_url"] is True
