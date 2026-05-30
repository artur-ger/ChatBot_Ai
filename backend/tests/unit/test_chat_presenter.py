from app.services.chat_presenter import present_chat_response, sanitize_user_answer_text
from app.schemas.chat import ChatResponse, SourceItem


def test_sanitize_removes_sources_block_with_bullets():
    raw = (
        "ЦФА учитываются при реализации.\n\n"
        "Источники:\n"
        "- [books.taxation] учету на дату реализации\n"
        "- [books.registration] енным ЦФА\n\n"
        "Уверенность: 0.68"
    )
    assert sanitize_user_answer_text(raw) == "ЦФА учитываются при реализации."


def test_present_chat_response_strips_metadata():
    response = present_chat_response(
        ChatResponse(
            text="Ответ пользователю",
            sources=[SourceItem(doc_id="books.taxation", snippet="фрагмент")],
            confidence=0.68,
            chat_id="web-1",
        )
    )
    assert response.text == "Ответ пользователю"
    assert response.sources == []
    assert response.confidence == 0.0
