# ChatBot AI

Бэкенд RAG-чата: загрузка документов, асинхронная индексация, векторный поиск и наблюдаемость.

Репозиторий подготовлен так, чтобы команда могла быстро запустить проект локально и развернуть его без лишной ручной настройки.

## Документация состояния проекта

- [docs/PROJECT_STATE.md](docs/PROJECT_STATE.md) — инвентаризация API и модулей
- [docs/ROLLOUT.md](docs/ROLLOUT.md) — runbook вывода в prod (KB, LLM, smoke, бэкапы)
- [docs/DEV2_TZ_AUDIT.md](docs/DEV2_TZ_AUDIT.md) — аудит зоны Telegram/worker

## Что реализовано

- FastAPI-бэкенд с версионированным API (`/api/v1`) и Swagger (`/docs`).
- Пайплайн загрузки документов (`/api/v1/documents`) с валидацией и асинхронными задачами индексации.
- Celery worker + Redis (broker/result backend).
- Интеграция с Chroma для семантического поиска.
- Эндпоинт чата (`/api/v1/chat`) с retrieval-контекстом, историей и reset.
- Системные/админ-эндпоинты (`/healthz`, `/readyz`, `/system/info`, reindex/retry/cancel).
- Docker Compose-стек для локалки: `backend`, `worker`, `postgres`, `redis`, `chroma`.
- CPU-only фиксация PyTorch, чтобы избежать таймаутов из-за CUDA-зависимостей.
- Общий кеш Hugging Face для `backend` и `worker`.
- Интеграционные и e2e тесты по основному и новому функционалу.

## Структура проекта

- `backend/` — код приложения, Dockerfile, compose-стек, тесты.
- `docker-compose.yml` (в корне) — обертка, позволяет запускать compose из корня репозитория.

## Быстрый старт для команды

### Вариант A: Полный запуск в Docker (рекомендуется)

Из корня репозитория:

```powershell
cd c:\ChatBot_Ai
copy .env.example .env
docker compose up --build
```

Открыть:

- Чат (пользователи): [http://localhost:8000/](http://localhost:8000/)
- Админ-панель (KB, LLM, задачи): [http://localhost:8000/admin](http://localhost:8000/admin) — логин/пароль из `.env` (`ADMIN_USERNAME` / `ADMIN_PASSWORD`, создаёт `init-env.ps1`)
- Swagger: [http://localhost:8000/docs](http://localhost:8000/docs)
- OpenAPI: [http://localhost:8000/openapi.json](http://localhost:8000/openapi.json)

### Вариант B: API локально через Poetry, зависимости в Docker

```powershell
cd c:\ChatBot_Ai\backend
copy .env.example .env
docker compose up -d postgres redis chroma
poetry config virtualenvs.in-project true --local
poetry env use 3.12
poetry install --with dev
poetry run alembic upgrade head
poetry run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## Важные переменные окружения

- Для Docker Compose основной env-файл: `.env` в корне (пример в `.env.example`).
- Для локального запуска через Poetry: `backend/.env` (пример в `backend/.env.example`).
- Для реальных эмбеддингов:
  - `USE_FAKE_EMBEDDINGS=false`
  - в контейнерах должен резолвиться `huggingface.co`.
- Для gated-моделей (опционально):
  - `HF_TOKEN` в корневом `.env` (Docker) или в `backend/.env` (Poetry).

## Порядок развертывания для команды

1. Забрать актуальный код.
2. Убедиться, что Docker Desktop запущен.
3. Создать/обновить `.env` в корне на основе `.env.example`.
4. Запустить:

```powershell
cd c:\ChatBot_Ai
docker compose up -d --build
```

5. Проверить состояние сервисов:

```powershell
docker compose ps
```

6. Проверить здоровье:

- `GET http://localhost:8000/healthz` (быстрый liveness)
- `GET http://localhost:8000/readyz` (готовность зависимостей)

## Docker: типичные ошибки

**`TLS handshake timeout` при `python:3.12-slim`** — Docker Hub недоступен с вашей сети (VPN, firewall). Решения:

1. Включить VPN и один раз: `docker pull python:3.12-slim`, затем `docker compose up -d --build`.
2. Зеркало в Yandex CR: `.\backend\scripts\push_mirror_images.ps1 -RegistryPrefix "cr.yandex.net/<id>"`, в `.env` задать `PYTHON_BASE_IMAGE=cr.yandex.net/<id>/python:3.12-slim`.

**Предупреждение `TELEGRAM_BOT_TOKEN` не задан** — нормально. Telegram-бот по умолчанию **не** поднимается. Для бота:

```powershell
# в .env: TELEGRAM_BOT_TOKEN=...
docker compose --profile telegram up -d --build
```

## Полезные команды

```powershell
# Первый запуск: .env + docker + smoke
cd c:\ChatBot_Ai\backend
.\scripts\init-env.ps1
.\scripts\deploy.ps1
# с ботом: .\scripts\deploy.ps1 -WithTelegram

# Go-live после загрузки KB и настройки LLM в /admin
.\scripts\go-live-checklist.ps1 -AdminUsername admin -AdminPassword "<из .env>"

# Бэкап PostgreSQL
.\scripts\backup.ps1

# Полный прогон тестов
poetry run pytest tests/unit tests/integration tests/e2e -q
```

## Ключевое поведение API

- `POST /api/v1/chat/{chat_id}/reset` удаляет только сообщения, а не "чат" как сущность.
- `POST /api/v1/indexing-tasks/{id}/retry` перезапускает только задачи со статусом `failed`.
- `POST /api/v1/indexing-tasks/{id}/cancel` отменяет задачу и чистит частичные данные в Chroma.
- `DELETE /api/v1/documents/{id}` удаляет запись в БД и связанные векторные чанки.

## Подробная документация бэкенда

См. `backend/README.md` — там подробно про локальный запуск, Yandex Container Registry, облачный деплой и сетевые нюансы.

