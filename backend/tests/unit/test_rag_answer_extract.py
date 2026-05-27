import pytest

from app.services.rag_answer_extract import (
    extract_faq_answer,
    generate_rule_based_answer,
)


def test_extract_faq_answer_picks_matching_question():
    context = """
    Вопрос: Как пополнить счет?
    Ответ: Перейдите в раздел пополнения баланса и выберите способ оплаты.

    Вопрос: Как восстановить доступ?
    Ответ: Нажмите «Восстановить пароль» на странице входа и следуйте инструкции.
    """
    answer = extract_faq_answer("как восстановить доступ?", context)
    assert answer is not None
    assert "восстанов" in answer.casefold()
    assert "пополн" not in answer.casefold()


def test_generate_rule_based_answer_from_prompt():
    prompt = """Инструкция.
Контекст:
[instructions.often_questions] Вопрос: Как пополнить счет? Ответ: Оплатите через банк.
[instructions.access_to_personal_account] Как восстановить доступ в личный кабинет? Нажмите восстановить пароль.
Вопрос: как восстановить доступ?"""
    answer = generate_rule_based_answer(prompt)
    assert "восстанов" in answer.casefold()
    assert "пополн" not in answer.casefold()


def test_generate_rule_based_answer_raises_on_llm_down_marker():
    from app.core.errors import DependencyAppError

    with pytest.raises(DependencyAppError):
        generate_rule_based_answer("trigger_llm_down test prompt")
