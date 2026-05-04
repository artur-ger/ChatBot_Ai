# ChatBot AI Backend

## Local development with Poetry

```powershell
poetry config virtualenvs.in-project true --local
poetry env use 3.12
poetry install --with dev
poetry run alembic upgrade head
poetry run pytest tests/unit tests/integration tests/e2e -q
poetry run uvicorn app.main:app --reload
```

## Quality gate (matches CI)

```powershell
$env:CELERY_BROKER_URL="memory://"
$env:CELERY_RESULT_BACKEND="cache+memory://"
$env:CELERY_TASK_ALWAYS_EAGER="true"
$env:CHROMA_HOST=""
$env:USE_FAKE_EMBEDDINGS="true"

poetry run ruff check .
poetry run black --check .
poetry run mypy app
poetry run pytest --cov=app --cov-report=term-missing --cov-fail-under=70 -q
```

## Docker

```powershell
docker compose up --build
```

Services:
- `backend`: FastAPI + Alembic migrations on startup
- `worker`: Celery worker for indexing
- `postgres`, `redis`, `chroma`

## Chat ACL and webhook alerts

- Chat isolation is enforced by `X-Chat-Signature` (HMAC-SHA256 over `chat_id`).
- Use `CHAT_ACL_SECRET` in environment to sign and verify chat requests.
- Optional critical-failure alert webhook can be configured with `ALERT_WEBHOOK_URL`.
