from __future__ import annotations

from app.services.rag_prompt_defaults import DEFAULT_RAG_SYSTEM_INSTRUCTION


def test_get_and_update_rag_prompt(client):
    get_response = client.get("/api/v1/admin/rag/prompt")
    assert get_response.status_code == 200, get_response.text
    initial = get_response.json()
    assert initial["system_instruction"] == DEFAULT_RAG_SYSTEM_INSTRUCTION
    assert initial["is_default"] is True
    assert initial["max_length"] == 4000

    custom = (
        "Ты консультант компании. Отвечай вежливо, кратко и только по документам базы знаний."
    )
    update_response = client.put(
        "/api/v1/admin/rag/prompt",
        json={"system_instruction": custom},
    )
    assert update_response.status_code == 200, update_response.text
    updated = update_response.json()
    assert updated["system_instruction"] == custom
    assert updated["is_default"] is False

    reset_response = client.post("/api/v1/admin/rag/prompt/reset")
    assert reset_response.status_code == 200
    reset_body = reset_response.json()
    assert reset_body["system_instruction"] == DEFAULT_RAG_SYSTEM_INSTRUCTION
    assert reset_body["is_default"] is True


def test_update_rag_prompt_validation(client):
    too_short = client.put(
        "/api/v1/admin/rag/prompt",
        json={"system_instruction": "коротко"},
    )
    assert too_short.status_code == 400
    assert too_short.json()["error_code"] == "validation_error"
