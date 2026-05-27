"""One-off GigaChat OAuth smoke test (optional, requires network).

Usage:
  poetry run python scripts/smoke_gigachat_auth.py --basic "Basic YOUR_KEY"
  poetry run python scripts/smoke_gigachat_auth.py --basic "Basic ..." --chat
"""

from __future__ import annotations

import argparse
import asyncio
import sys


async def main() -> int:
    parser = argparse.ArgumentParser(description="GigaChat OAuth smoke test")
    parser.add_argument(
        "--basic",
        required=True,
        help="Authorization Basic ... (тот же ключ, что в админке LLM integrations)",
    )
    parser.add_argument("--chat", action="store_true", help="Also run a chat completion")
    parser.add_argument("--model", default="GigaChat", help="Model name for --chat")
    args = parser.parse_args()

    from app.services.gigachat_auth import get_gigachat_token_manager

    try:
        token = await get_gigachat_token_manager(authorization_key=args.basic).get_token(force=True)
    except Exception as exc:
        print(f"FAIL oauth: {exc}")
        return 1

    print(f"OK oauth: access_token length={len(token)}")

    if args.chat:
        from app.services.llm_client import build_llm_client

        client = build_llm_client(
            provider="gigachat",
            model=args.model,
            base_url=None,
            api_key=args.basic,
        )
        try:
            answer = await client.generate("Ответь одним словом: pong")
        except Exception as exc:
            print(f"FAIL chat: {exc}")
            return 1
        print(f"OK chat: {answer[:120]}")

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
