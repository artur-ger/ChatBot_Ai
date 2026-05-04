from __future__ import annotations

import time
from unittest.mock import patch

import app.workers.tasks_indexing as indexing_tasks


def test_upload_indexes_document(client):
    webhook_calls: list[dict[str, object]] = []

    def fake_send_webhook(*, url: str, secret: str | None, payload: dict[str, object]) -> None:
        webhook_calls.append({"url": url, "secret": secret, "payload": payload})

    files = {
        "file": (
            "note.txt",
            b"Hello world from ingestion test.\n\nSecond paragraph.",
            "text/plain",
        ),
    }
    data = {"callback_url": "https://example.com/webhook", "webhook_secret": "secret"}

    with patch.object(indexing_tasks, "_send_webhook", side_effect=fake_send_webhook):
        response = client.post("/api/v1/documents", files=files, data=data)

    assert response.status_code == 202, response.json()
    body = response.json()
    assert body["status"] in {"pending", "processing", "indexed", "failed"}

    task_id = body["task_id"]
    deadline = time.time() + 15
    task_payload: dict[str, object] = {}
    while time.time() < deadline:
        task_response = client.get(f"/api/v1/indexing-tasks/{task_id}")
        assert task_response.status_code == 200
        task_payload = task_response.json()
        if task_payload["status"] in {"indexed", "failed"}:
            break
        time.sleep(0.75)

    doc_debug = client.get(f"/api/v1/documents/{body['document_id']}")
    assert doc_debug.status_code == 200, doc_debug.text
    doc_debug_json = doc_debug.json()

    assert task_payload["status"] == "indexed", {"task": task_payload, "document": doc_debug_json}

    doc_response = client.get(f"/api/v1/documents/{body['document_id']}")
    assert doc_response.status_code == 200
    assert doc_response.json()["status"] == "indexed"

    assert webhook_calls, "webhook should be attempted on success"
    assert webhook_calls[0]["payload"]["status"] == "indexed"
    assert webhook_calls[0]["secret"] == "secret"
