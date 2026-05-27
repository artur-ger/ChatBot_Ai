# Аудит ТЗ второго бэкенд-разработчика

Сверка с репозиторием на **2026-05-19**. Цель документа — зафиксировать зону ответственности Dev2, чтобы при работе Dev1 (API, LLM, админка) **не удалять** эти модули.

## Файлы зоны Dev2 (не удалять)

| Область | Пути |
|---------|------|
| Telegram-бот | `backend/telegram_bot/app/main.py`, `core_api.py`, `config.py`, `storage.py`, `Dockerfile`, `requirements.txt` |
| Celery | `backend/app/workers/celery_app.py`, `tasks.py`, `tasks_indexing.py`, `async_runner.py` |
| Парсинг / чанки | `backend/app/services/text_extract.py`, `text_chunking.py`, `ingestion_service.py` |
| Chroma | `backend/app/integrations/chroma_store.py` |
| API загрузки (контракт для бота) | `backend/app/api/documents.py`, `indexing_tasks.py` |
| Модели | `backend/app/models/document.py`, `indexing_task.py` |
| Compose | `backend/docker-compose.yml` — сервисы `worker`, `telegram-bot` (profile `telegram`) |

## Проверка работоспособности (локально)

```text
cd backend && poetry run pytest tests/unit tests/integration tests/e2e -q
# Результат: 15 passed (2026-05-19)

poetry run python -m compileall telegram_bot/app -q
# OK — синтаксис бота
```

Интеграционный тест `test_upload_indexes_document` прогоняет полный пайплайн: upload → Celery (eager в тестах) → extract → chunk → embed → Chroma → status `indexed`.

Запуск бота в Docker: `docker compose --profile telegram up -d` + `TELEGRAM_BOT_TOKEN` в корневом `.env`.

---

## Сводка по ТЗ

| Требование ТЗ | Статус | Где в коде / комментарий |
|---------------|--------|---------------------------|
| **Telegram: aiogram 3** | ✅ | `telegram_bot/requirements.txt` — aiogram `>=3.13` |
| **FSM состояний диалога** | ⚠️ частично | `MemoryStorage` подключён, отдельных `StatesGroup` нет; UX через клавиатуру и хендлеры |
| **Команды start, help** | ✅ | `Command("start")`, `Command("help")` |
| **Очистка истории чата** | ⚠️ | `CoreApiClient.reset_chat()` есть, **команды /reset в боте нет** |
| **Прокси в Core API `/chat`** | ✅ | `core_api.send_message` → `POST /chat` |
| **Загрузка файлов через API** | ✅ | `upload_document` → `POST /documents` |
| **Индикатор «печатает»** | ✅ | `send_chat_action(..., "typing")` |
| **Длинные ответы — части** | ✅ | `split_telegram_text`, `send_long_message` |
| **Retry при недоступности API** | ✅ | 3 попытки, backoff в `core_api._request_with_retries` |
| **Graceful degradation** | ✅ | «Сервис временно недоступен…» |
| **Структурированное JSON-логирование в боте** | ❌ | `logging.basicConfig(level=INFO)`; JSON — в основном API (`app/observability/logging.py`) |
| **Форматы TXT, PDF, DOCX** | ✅ | `text_extract.py` (pypdf, python-docx), валидация MIME в `ingestion_service.py` |
| **Валидация размера/типа** | ✅ | `max_upload_bytes`, `allowed_mime_types` |
| **Временное хранилище + UUID** | ✅ | `save_upload_to_temp`, `documents.temp_path` |
| **Асинхронная задача индексации** | ✅ | `index_document.apply_async` |
| **Очистка текста, чанки с overlap** | ✅ | `text_chunking.chunk_text` |
| **Embeddings + ChromaDB** | ✅ | `tasks_indexing._index_document_async`, `ChromaVectorStore` |
| **Статусы pending → processing → indexed/failed** | ✅ | обновления в `tasks_indexing` + API |
| **Celery + Redis broker/backend** | ✅ | `celery_app.py`, compose `worker` |
| **Автоповторы задач** | ✅ | `max_retries=5`, `autoretry_for=(Exception,)` |
| **Ограничение параллелизма** | ✅ | worker `--concurrency=1`, `worker_prefetch_multiplier=1` |
| **Метаданные задач в PostgreSQL** | ⚠️ | `id`, `status`, `celery_task_id`, `error_message`, `created_at`, `updated_at`; **отдельного поля «число попыток» нет** |
| **Периодические health-check воркеров** | ❌ | Celery Beat / periodic tasks не настроены |
| **Graceful shutdown воркеров** | ⚠️ | стандартное поведение Celery; явной настройки сигналов в репо нет |
| **Асинхронный клиент Chroma с пулом** | ❌ | синхронный `chromadb.HttpClient` внутри async-задачи через `run_async` |
| **Unit-тесты парсеров** | ❌ | нет `test_text_extract.py` / `test_text_chunking.py` |
| **Интеграционные тесты Redis/Chroma** | ⚠️ | `test_ingestion_upload` (eager Celery, fake embeddings в conftest) |
| **Тесты бота с моками API** | ❌ | отдельного пакета `tests/telegram_bot/` нет |
| **Docker: отдельные образы бот + worker** | ✅ | `telegram_bot/Dockerfile`, worker из `backend/Dockerfile` |
| **Healthcheck в compose** | ⚠️ | postgres, redis; **нет** для worker и telegram-bot |
| **Multi-stage образы** | ❌ | single-stage Dockerfiles |
| **PEP8 / ruff / mypy** | ⚠️ | настроено для основного `backend/`; бот — отдельный `requirements.txt`, без Poetry |

---

## Дополнительно реализовано (сверх минимального ТЗ)

- Локальное хранилище связей chat_id ↔ document_id (`telegram_bot/app/storage.py`, SQLite).
- Опрос статуса индексации после загрузки (`poll_indexing_status`).
- Кнопки: «Мои документы», «Статус сервиса», загрузка файлов.
- Webhook при успехе/ошибке индексации (`tasks_indexing._send_webhook`).
- Retry/cancel задач через API (`indexing_tasks.py`).
- Поддержка `.md` в боте и ingestion.
- `POST /documents/kb-archive` — зона Dev1/KB, но использует тот же worker.

---

## Рекомендации (не блокируют совместную работу)

1. Добавить в бота `/reset` → `core_api.reset_chat`.
2. При желании — FSM для сценария «ожидаю файл после нажатия Загрузить».
3. Unit-тесты на `extract_text_from_file` и `chunk_text`.
4. JSON-логирование в `telegram_bot` по образцу API.
5. Поле `attempt_count` в `indexing_tasks` — если нужен аудит из ТЗ дословно.

---

## Граница Dev1 / Dev2

| Dev2 (не ломать контракт) | Dev1 (можно развивать отдельно) |
|---------------------------|----------------------------------|
| Формат `POST /api/v1/chat`, `sources` | LLM integrations, admin API |
| `POST /api/v1/documents`, статусы документов | `kb-archive`, статика `/` и `/admin` |
| Celery task `index_document` | RAG prompt, rate limits, ACL |
| Chroma collection `kb_{embedding_model_version}` | |

При изменении `chunk_size`, `embedding_model_version` или схемы метаданных Chroma — согласовать с Dev2 / переиндексация.
