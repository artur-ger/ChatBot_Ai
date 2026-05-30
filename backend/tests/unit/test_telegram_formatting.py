from __future__ import annotations

import importlib
import sys
from pathlib import Path


TELEGRAM_APP_DIR = Path(__file__).resolve().parents[2] / "telegram_bot" / "app"
if str(TELEGRAM_APP_DIR) not in sys.path:
    sys.path.insert(0, str(TELEGRAM_APP_DIR))

formatting = importlib.import_module("formatting")


def test_parse_chat_reply() -> None:
    reply = formatting.parse_chat_reply(
        {
            "text": "Ответ",
            "sources": [{"doc_id": "doc-1", "snippet": "Фрагмент"}],
            "confidence": 0.87,
        }
    )
    assert reply.text == "Ответ"
    assert reply.sources[0]["doc_id"] == "doc-1"
    assert reply.confidence == 0.87


def test_format_sources_block() -> None:
    block = formatting.format_sources_block([{"doc_id": "abc", "snippet": "x" * 200}])
    assert "Источники:" in block
    assert "abc" in block
    assert "…" in block


def test_format_chat_message() -> None:
    message = formatting.format_chat_message(
        formatting.ChatReply(
            text="Готово",
            sources=[{"doc_id": "doc-1", "snippet": "snippet"}],
            confidence=0.75,
        )
    )
    assert message == "Готово"
    assert "[doc-1]" not in message
    assert "0.75" not in message

