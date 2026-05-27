# Состояние проекта ChatBot AI (зафиксировано)



Документ описывает, что уже реализовано. **Не удалять** перечисленные модули без явного решения команды.



## Стек



| Компонент | Технология |

|-----------|------------|

| API | FastAPI, `/api/v1` |

| БД | PostgreSQL + SQLAlchemy async + Alembic |

| Очередь | Celery + Redis |

| Векторы | ChromaDB |

| Embeddings | sentence-transformers (CPU), `USE_FAKE_EMBEDDINGS` для тестов |

| LLM | Плагинная модель: `openai_compatible`, `rule_based` + таблица `llm_integrations` |

| Фронт | Статика в `backend/app/static/` |

| Бот | `backend/telegram_bot/` → тот же REST API |

| Deploy | Корневой `docker-compose.yml`, `.env` в корне |



## API (бэкенд)



### Система

- `GET /healthz`, `GET /readyz`

- `GET /system/info` — LLM, embedding, интеграции

- `GET /system/ui-config` — `show_admin_link`, `chat_acl_required`



### Чат (публичный)

- `POST /api/v1/chat` — RAG, `text`, `sources`, `confidence`

- `GET /api/v1/chat/{chat_id}/history`

- `POST /api/v1/chat/{chat_id}/reset`



### Документы (admin auth)

- `POST /api/v1/documents` — 202, файл

- `POST /api/v1/documents/kb-archive` — 202, zip + YAML manifest

- `GET /api/v1/documents`, `GET /api/v1/documents/{id}`, `DELETE /api/v1/documents/{id}`



### Задачи индексации (admin auth)

- `GET /api/v1/indexing-tasks`, `GET /api/v1/indexing-tasks/{id}`

- `POST .../retry`, `POST .../cancel`



### Админ-авторизация

- `POST /api/v1/admin/login` — логин/пароль → HttpOnly cookie `admin_session`

- `POST /api/v1/admin/logout`

- Bearer `ADMIN_API_TOKEN` — для скриптов и Telegram-бота



### Админ API (cookie или Bearer)

- `POST /api/v1/admin/reindex`

- `GET|PUT /api/v1/admin/rag/prompt`, `POST .../reset`

- `GET|POST /api/v1/admin/llm/integrations`

- `GET|PUT|DELETE /api/v1/admin/llm/integrations/{id}`

- `POST .../activate`, `POST .../test`



## Модели БД



- `chat_messages`

- `documents`, `indexing_tasks`, `webhook_subscriptions`

- `llm_integrations` (миграция `20260519_0003`)

- `rag_prompt_settings` (миграция `20260519_0004`, singleton `default`)



## Ключевые сервисы



- `app/services/rag_pipeline.py` — retrieval, prompt, LLM через `LlmClientFactory`

- `app/services/rag_prompt_service.py` — кеш промпта из БД

- `app/services/llm_factory.py` — активная интеграция из БД, кеш, fallback `rule_based`

- `app/services/kb_archive_import.py` — парсинг `kb.zip`

- `app/workers/tasks_indexing.py` — индексация, webhooks, reindex



## Фронтенд



- `/` — `index.html` + `common.js` + `chat.js` (только чат)

- `/admin` — `admin.html` + `common.js` + `admin.js` (KB, LLM, промпт, задачи)

- Автообновление статусов документов/задач каждые 3 с при `pending`/`processing`

- `app.js` — legacy, не подключается страницами



## Telegram-бот



- aiogram 3, прокси в Core API

- Ответы с источниками и confidence

- `/reset`, условная загрузка документов при `ADMIN_API_TOKEN` в env

- `formatting.py` — форматирование сообщений



## Переменные окружения (важные)



| Переменная | Назначение |

|------------|------------|

| `ADMIN_USERNAME`, `ADMIN_PASSWORD` | Вход в `/admin` (UI) |

| `ADMIN_SESSION_SECRET` | Подпись cookie-сессии |

| `ADMIN_API_TOKEN` | Bearer для API/бота/скриптов |

| `CHAT_ACL_DISABLED` | `true` — веб-чат без подписи (локально) |

| `LLM_SETTINGS_ENCRYPTION_KEY` | Fernet для API keys в БД |

| `LLM_ALLOW_RULE_BASED_FALLBACK` | Без активной LLM → rule_based |

| `PUBLIC_SHOW_ADMIN_LINK` | Ссылка на `/admin` на главной |

| `HF_TOKEN`, `USE_FAKE_EMBEDDINGS` | Embeddings |

| `TELEGRAM_BOT_TOKEN` | Профиль `telegram` в compose |



Compose: `env_file: ../.env` в `backend/docker-compose.yml` (файл в **корне** репозитория).



## Скрипты (backend/scripts)



- `init-env.ps1` — `.env`, токены, пароль admin, Fernet, `CHAT_ACL_DISABLED`

- `deploy.ps1` — compose up + smoke + go-live

- `smoke.ps1` — health, chat, admin cookie/token

- `go-live-checklist.ps1` — проверка перед выдачей пользователям

- `backup.ps1` — dump PostgreSQL



## Тесты



- **32 passed** — unit, integration, e2e

- `test_admin_auth.py` — Bearer + cookie login

- `test_rag_prompt.py`, `test_llm_integrations.py`

- `test_text_pipeline.py`, `test_telegram_formatting.py`



## Не трогать без необходимости



- Логику индексации/Celery/Chroma

- Контракты `/api/v1/chat` и формат `sources`

- Шифрование ключей LLM

- Telegram `core_api.py` (те же пути API)

