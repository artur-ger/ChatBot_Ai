from __future__ import annotations

from app.services.rag_answer_extract import (
    extract_context_chunks_from_prompt,
    generate_rule_based_answer,
)
from app.services.rag_prompt_defaults import DEFAULT_RAG_SYSTEM_INSTRUCTION


def main() -> None:
    snippet = (
        "Как пополнить счет физическому лицу в личном кабинете http://lk.tokeon.ru.\n"
        "1. Перейдите в личный кабинет"
    )
    prompt = (
        f"{DEFAULT_RAG_SYSTEM_INSTRUCTION}\n"
        "История (если есть):\n\n"
        "Контекст:\n"
        f"[instructions.account] {snippet}\n"
        "Вопрос: как пополнить счет?"
    )
    chunks = extract_context_chunks_from_prompt(prompt)
    with open("parse_test.txt", "w", encoding="utf-8") as fh:
        fh.write(f"chunks={len(chunks)}\n")
        for item in chunks:
            fh.write(repr(item) + "\n")
        fh.write("\nANSWER:\n")
        fh.write(generate_rule_based_answer(prompt))


if __name__ == "__main__":
    main()
