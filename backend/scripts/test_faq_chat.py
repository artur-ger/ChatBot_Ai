from __future__ import annotations

import httpx

QUERIES = [
    "как восстановить доступ?",
    "как пополнить счет?",
]


def main() -> None:
    for query in QUERIES:
        response = httpx.post(
            "http://localhost:8000/api/v1/chat",
            json={"text": query, "chat_id": "debug-faq"},
            timeout=120.0,
        )
        response.raise_for_status()
        data = response.json()
        print(f"=== {query} ===")
        print(data["text"][:700])
        print("sources:", [item["doc_id"] for item in data.get("sources", [])])
        print()


if __name__ == "__main__":
    main()
