from __future__ import annotations

from app.services.llm_client import BaseLlmClient
from app.services.llm_factory import ActiveLlmContext


class StubLlmFactory:
    def __init__(self, client: BaseLlmClient, *, model_name: str = "stub-model") -> None:
        self._client = client
        self._model_name = model_name

    def invalidate_cache(self) -> None:
        return None

    async def get_active_context(self) -> ActiveLlmContext:
        return ActiveLlmContext(
            client=self._client,
            model_name=self._model_name,
            integration_id="stub-integration",
            provider="rule_based",
        )
