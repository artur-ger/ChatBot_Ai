import asyncio
import re
import time
from collections import OrderedDict

from app.core.config import settings
from app.core.errors import DependencyAppError, ValidationAppError
from app.schemas.chat import ChatResponse, SourceItem
from app.services.llm_factory import LlmClientFactory
from app.services.chat_presenter import sanitize_user_answer_text
from app.services.kb_index_health import get_kb_index_status
from app.services.rag_grounding import (
    INSUFFICIENT_ANSWER_TEXT,
    extract_grounded_answer,
    is_likely_hallucination,
    should_use_extractive_answer,
)
from app.services.rag_prompt_defaults import DEFAULT_RAG_SYSTEM_INSTRUCTION
from app.services.rag_prompt_service import RagPromptService
from app.services.retriever import BaseRetriever, RetrievedChunk


class RagPipeline:
    def __init__(
        self,
        retriever: BaseRetriever,
        llm_factory: LlmClientFactory,
        rag_prompt_service: RagPromptService | None = None,
    ) -> None:
        self.retriever = retriever
        self.llm_factory = llm_factory
        self.rag_prompt_service = rag_prompt_service
        self._cache: OrderedDict[str, tuple[float, ChatResponse, list[float]]] = OrderedDict()
        self._llm_failures = 0
        self._circuit_open_until = 0.0

    def normalize_query(self, text: str) -> str:
        stripped = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text)
        normalized = " ".join(stripped.split()).strip()
        if len(normalized) < 2:
            raise ValidationAppError("Text is too short after normalization")
        lowered = normalized.casefold()
        suspicious_markers = (
            "ignore previous instructions",
            "ignore all previous",
            "system prompt",
            "you are now",
            "jailbreak",
            "developer mode",
        )
        if any(marker in lowered for marker in suspicious_markers):
            raise ValidationAppError("Question was rejected by safety filters")
        return normalized

    def filter_and_deduplicate(self, chunks: list[RetrievedChunk]) -> list[RetrievedChunk]:
        seen: set[tuple[str, str]] = set()
        filtered: list[RetrievedChunk] = []
        for chunk in chunks:
            if chunk.score < settings.min_chunk_score:
                continue
            key = (chunk.doc_id, chunk.snippet)
            if key in seen:
                continue
            seen.add(key)
            filtered.append(chunk)
        return filtered

    def calculate_confidence(self, chunks: list[RetrievedChunk]) -> float:
        if not chunks:
            return 0.25
        score = sum(chunk.score for chunk in chunks[:3]) / min(3, len(chunks))
        return max(0.0, min(round(score, 3), 1.0))

    def build_prompt(
        self,
        question: str,
        chunks: list[RetrievedChunk],
        history: list[tuple[str, str]],
        *,
        system_instruction: str | None = None,
    ) -> str:
        instruction = (system_instruction or DEFAULT_RAG_SYSTEM_INSTRUCTION).strip()
        context = "\n".join([f"[{c.doc_id}] {c.snippet}" for c in chunks[:3]])
        history_lines: list[str] = []
        history_budget = settings.chat_history_max_chars
        for role, message in reversed(history):
            line = f"{role}: {message}"
            if history_budget - len(line) < 0:
                break
            history_lines.append(line)
            history_budget -= len(line)
        history_block = "\n".join(reversed(history_lines))
        return (
            f"{instruction}\n"
            "Правила ответа:\n"
            "- Используй только факты из блока «Контекст».\n"
            "- Не добавляй методы, термины и рекомендации, которых нет в контексте.\n"
            f"- Если ответа в контексте нет, напиши дословно: «{INSUFFICIENT_ANSWER_TEXT}»\n"
            f"История (если есть):\n{history_block}\n"
            f"Контекст:\n{context}\n"
            f"Вопрос: {question}"
        )

    def _cache_key(self, *, chat_id: str, question: str) -> str:
        return f"{chat_id}:{question.casefold()}"

    def _get_cached(
        self, *, chat_id: str, question: str
    ) -> tuple[ChatResponse, list[float]] | None:
        key = self._cache_key(chat_id=chat_id, question=question)
        payload = self._cache.get(key)
        if payload is None:
            return None
        expires_at, response, retrieval_scores = payload
        if time.time() > expires_at:
            self._cache.pop(key, None)
            return None
        self._cache.move_to_end(key)
        return response, retrieval_scores

    def _set_cache(
        self,
        *,
        chat_id: str,
        question: str,
        response: ChatResponse,
        retrieval_scores: list[float],
    ) -> None:
        key = self._cache_key(chat_id=chat_id, question=question)
        self._cache[key] = (time.time() + settings.chat_cache_ttl_sec, response, retrieval_scores)
        self._cache.move_to_end(key)
        while len(self._cache) > settings.chat_cache_max_items:
            self._cache.popitem(last=False)

    def _sanitize_answer_text(self, text: str) -> str:
        return sanitize_user_answer_text(text)

    def _postprocess_answer(
        self, text: str, sources: list[SourceItem]
    ) -> tuple[str, list[SourceItem]]:
        return self._sanitize_answer_text(text), sources

    async def _generate_with_retry(self, prompt: str) -> str:
        llm_context = await self.llm_factory.get_active_context()
        last_error: Exception | None = None
        for _ in range(settings.llm_retry_attempts + 1):
            try:
                return await asyncio.wait_for(
                    llm_context.client.generate(prompt),
                    timeout=settings.llm_timeout_seconds,
                )
            except (TimeoutError, asyncio.TimeoutError, DependencyAppError) as exc:
                last_error = exc
        raise DependencyAppError(str(last_error) if last_error else "LLM failed")

    async def answer(
        self,
        question: str,
        chat_id: str,
        history: list[tuple[str, str]] | None = None,
    ) -> tuple[ChatResponse, list[float]]:
        normalized_question = self.normalize_query(question)
        cached = self._get_cached(chat_id=chat_id, question=normalized_question)
        if cached is not None:
            return cached

        kb_index = await get_kb_index_status()
        if not kb_index.is_searchable and kb_index.message:
            response = ChatResponse(
                text=kb_index.message,
                sources=[],
                confidence=0.0,
                chat_id=chat_id,
            )
            return response, []

        chunks = await self.retriever.retrieve(normalized_question, settings.retriever_top_k)
        context_chunks = self.filter_and_deduplicate(chunks)
        confidence = self.calculate_confidence(context_chunks)
        sources = [
            SourceItem(
                doc_id=chunk.doc_id,
                snippet=chunk.snippet,
                doc_type=chunk.doc_type,
                document_date=chunk.document_date,
            )
            for chunk in context_chunks[:3]
        ]
        retrieval_scores = [chunk.score for chunk in context_chunks[:3]]
        context_text = "\n".join(chunk.snippet for chunk in context_chunks[:3])

        if not context_chunks:
            response = ChatResponse(
                text="Недостаточно данных в индексе для точного ответа.",
                sources=[],
                confidence=confidence,
                chat_id=chat_id,
            )
            return response, []

        if should_use_extractive_answer(normalized_question, context_chunks):
            extracted = extract_grounded_answer(normalized_question, context_chunks)
            if extracted:
                response = ChatResponse(
                    text=self._sanitize_answer_text(extracted),
                    sources=sources,
                    confidence=confidence,
                    chat_id=chat_id,
                )
                self._set_cache(
                    chat_id=chat_id,
                    question=normalized_question,
                    response=response,
                    retrieval_scores=retrieval_scores,
                )
                return response, retrieval_scores

        if self.rag_prompt_service is not None:
            system_instruction = await self.rag_prompt_service.get_system_instruction()
        else:
            system_instruction = DEFAULT_RAG_SYSTEM_INSTRUCTION
        prompt = self.build_prompt(
            normalized_question,
            context_chunks,
            history or [],
            system_instruction=system_instruction,
        )
        if time.time() < self._circuit_open_until:
            response = ChatResponse(
                text="Сервис генерации временно недоступен. Попробуйте позже.",
                sources=sources,
                confidence=max(0.0, confidence - 0.2),
                chat_id=chat_id,
            )
            return response, retrieval_scores
        try:
            text = await self._generate_with_retry(prompt)
            self._llm_failures = 0
            self._circuit_open_until = 0.0
        except DependencyAppError:
            self._llm_failures += 1
            if self._llm_failures >= settings.llm_circuit_breaker_threshold:
                self._circuit_open_until = time.time() + settings.llm_circuit_breaker_cooldown_sec
            response = ChatResponse(
                text="Сервис генерации временно недоступен. Попробуйте позже.",
                sources=sources,
                confidence=max(0.0, confidence - 0.2),
                chat_id=chat_id,
            )
            return response, retrieval_scores

        final_text, final_sources = self._postprocess_answer(text, sources)
        if is_likely_hallucination(final_text, context_text):
            extracted = extract_grounded_answer(normalized_question, context_chunks)
            final_text = extracted or INSUFFICIENT_ANSWER_TEXT
            final_text = self._sanitize_answer_text(final_text)
        response = ChatResponse(
            text=final_text,
            sources=final_sources,
            confidence=confidence,
            chat_id=chat_id,
        )
        self._set_cache(
            chat_id=chat_id,
            question=normalized_question,
            response=response,
            retrieval_scores=retrieval_scores,
        )
        return response, retrieval_scores
