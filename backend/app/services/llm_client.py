import asyncio

from app.core.errors import DependencyAppError


class BaseLlmClient:
    async def generate(self, prompt: str) -> str:
        raise NotImplementedError


class RuleBasedLlmClient(BaseLlmClient):
    async def generate(self, prompt: str) -> str:
        await asyncio.sleep(0)
        if "trigger_llm_down" in prompt:
            raise DependencyAppError("LLM service is unavailable")
        return f"Ответ сформирован на основе контекста: {prompt[:240]}"
