from __future__ import annotations

import httpx

QUERIES = {
    "restore": "\u043a\u0430\u043a \u0432\u043e\u0441\u0441\u0442\u0430\u043d\u043e\u0432\u0438\u0442\u044c \u0434\u043e\u0441\u0442\u0443\u043f?",
    "topup": "\u043a\u0430\u043a \u043f\u043e\u043f\u043e\u043b\u043d\u0438\u0442\u044c \u0441\u0447\u0435\u0442?",
}


def main() -> None:
    lines: list[str] = []
    for label, text in QUERIES.items():
        response = httpx.post(
            "http://localhost:8000/api/v1/chat",
            json={"text": text, "chat_id": f"verify-{label}"},
            timeout=120.0,
        )
        response.raise_for_status()
        data = response.json()
        sources = [item["doc_id"] for item in data.get("sources", [])]
        lines.append(f"=== {label} ===")
        lines.append(f"sources: {sources}")
        lines.append(data.get("text", "")[:500])
        lines.append("")

    output = "\n".join(lines)
    print(output)
    with open("faq_live_verify.txt", "w", encoding="utf-8") as fh:
        fh.write(output)


if __name__ == "__main__":
    main()
