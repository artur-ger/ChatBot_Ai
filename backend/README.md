# ChatBot AI Backend

## Быстрый старт без «сюрпризов» (локально)

1. Подними **PostgreSQL** и **Redis** (например `docker compose up -d postgres redis chroma` из корня репозитория — см. ниже, или свои инстансы).
2. Из корня репозитория подготовь env для локального режима backend:

```powershell
copy backend/.env.example backend/.env
cd backend
poetry config virtualenvs.in-project true --local
poetry env use 3.12
poetry install --with dev
poetry run alembic upgrade head
poetry run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

3. Открой **http://127.0.0.1:8000/docs** — в `.env.example` по умолчанию **`CHAT_ACL_DISABLED=true`**, заголовок `X-Chat-Signature` для чата **не нужен**.

Если Docker Hub с твоей сети **таймаутится**, см. раздел **«Образы в облаке (Yandex CR и др.)»** ниже — тогда `docker compose` тянет Postgres/Redis/Chroma **с твоего registry**, а не с `registry-1.docker.io`.

Если Hub доступен, при рабочем интернете один раз можно вручную:  
`docker pull postgres:15-alpine`, `docker pull redis:7-alpine`, `docker pull chromadb/chroma:1.5.8` — дальше в compose **`pull_policy: missing`**: при повторном `docker compose up` лишний раз в Hub не ходит.

## Образы в облаке (чтобы локально ставилось без Docker Hub)

Идея: **один раз** (на машине с нормальным интернетом или в CI) залить копии официальных образов в **Yandex Container Registry** (или любой другой Docker registry), а в репозитории в корневом `.env` указать полные имена — `docker-compose.yml` уже читает переменные **`POSTGRES_IMAGE`**, **`REDIS_IMAGE`**, **`CHROMA_IMAGE`** (если не заданы — остаются дефолты с Hub).

### Шаги (Yandex Cloud)

1. Создай **Container Registry** и три Docker-репозитория: **`postgres`**, **`redis`**, **`chroma`** (имена как в примере ниже).
2. Выполни **`docker login cr.yandex.net`** (команда из консоли Yandex / документации).
3. На машине, где `docker pull` с Hub **работает**, из корня репозитория:

```powershell
.\backend\scripts\push_mirror_images.ps1 -RegistryPrefix "cr.yandex.net/<registry-id>"
```

4. В корневой **`.env`** добавь строки, которые скрипт выведет в конце, например:

```env
POSTGRES_IMAGE=cr.yandex.net/<registry-id>/postgres:15-alpine
REDIS_IMAGE=cr.yandex.net/<registry-id>/redis:7-alpine
CHROMA_IMAGE=cr.yandex.net/<registry-id>/chroma:1.5.8
```

5. Локально: `docker compose up -d postgres redis chroma` из корня — тянется уже **с Yandex CR**.

Другой облачный registry — тот же сценарий: поменяй префикс в скрипте/`.env` на свой хост и путь репозиториев.

## Сервисы в Yandex Cloud (реально крутятся в облаке, не только образы)

Ниже — если нужно **не кэшировать образы**, а **поднять БД/кэш/векторы как сервисы** в Yandex. В консоли: [console.yandex.cloud](https://console.yandex.cloud).

### PostgreSQL

1. **Managed Service for PostgreSQL** → создать кластер (версия 15+, зона, сеть VPC).
2. Создать пользователя/БД под приложение (например БД `chatbot_ai`, пользователь `chatbot`).
3. Взять **FQDN хоста** и порт из карточки кластера, включить при необходимости **SSL** (у Yandex есть CA и режим `verify-full` — строку подключения смотри в документации к Managed PG для `asyncpg`).
4. В `.env` приложения выставить **`DATABASE_URL=postgresql+asyncpg://...`** на этот хост (не `postgres` из compose).

### Redis

1. **Managed Service for Valkey** (или **Managed Redis**, если доступен в твоём каталоге) → кластер.
2. Скопировать **подключение** (хост, порт, пароль, TLS при необходимости).
3. В `.env`: **`CELERY_BROKER_URL`**, **`CELERY_RESULT_BACKEND`** на managed Redis (часто `rediss://` если TLS).

### Chroma (векторное хранилище)

Отдельного «Managed Chroma» в Yandex обычно **нет**. Варианты:

1. **Compute Cloud (ВМ)** в той же VPC: установить Docker, запустить контейнер `chromadb/chroma` (как в нашем compose), открыть порт только из VPC / security group. В приложении: **`CHROMA_HOST=<внутренний_IP_или_FQDN>`**, **`CHROMA_PORT=8000`** (или как пробросишь).
2. **Managed Kubernetes** — Deployment + Service для образа Chroma (сложнее, но «по-облачному»).
3. **Без отдельного сервера Chroma** — в коде поддерживается режим **`CHROMA_HOST=`** пустой и **`CHROMA_PERSIST_PATH`** на диске (удобно для одной ВМ с API, без отдельного Chroma-контейнера).

### Сеть и безопасность

- Кластеры **Managed PG / Redis** и ВМ с Chroma должны быть в **одной VPC** (или связаны peering), а приложение — ходить по **внутренним** адресам, без публикации БД в интернет.
- Секреты (пароли БД, Redis) — только в **Lockbox** / переменных окружения на ВМ, не в Git.

### Связка с этим репозиторием

- Если Postgres/Redis/Chroma **в облаке**, локально **не обязательно** поднимать их через `docker compose`: достаточно `.env` с URL на Yandex и `poetry run uvicorn` (или свой деплой API в Compute/K8s).
- **Container Registry** из предыдущего раздела нужен, если хочешь **не зависеть от Docker Hub** при сборке/выкатке **своих** образов `backend`/`worker`.

## Только зависимости в Docker (API на хосте через Poetry)

Из корня репозитория:

```powershell
docker compose up -d postgres redis chroma
```

Порты: Postgres `5432`, Redis `6379`, Chroma UI/API `8001`. В `.env` укажи `DATABASE_URL`, `CELERY_*`, для Chroma в Docker — `CHROMA_HOST=localhost`, `CHROMA_PORT=8001` (или смотри `docker-compose.yml`).

## Полный стек в Docker (API + worker + всё остальное)

```powershell
cd c:\ChatBot_Ai
docker compose up --build
```

В корне лежит обёртка **`docker-compose.yml`**, которая подключает этот файл.

В контейнерах для удобства dev включено **`CHAT_ACL_DISABLED=true`** (подпись чата не требуется). **В продакшене** задай `CHAT_ACL_DISABLED=false` и обязательный `X-Chat-Signature`.

В **`docker-compose.yml`** по умолчанию **`USE_FAKE_EMBEDDINGS=false`**: поднимается реальная модель с Hugging Face. У сервисов **`backend`**, **`worker`** и **`chroma`** заданы публичные **`dns: 8.8.8.8, 1.1.1.1`** — часто это возвращает резолвинг **`huggingface.co`** при VPN и Docker Desktop. Том **`huggingface_cache`** смонтирован в **`HF_HOME=/root/.cache/huggingface`** (общий для API и worker), чтобы веса не скачивались заново после пересборки образа.

В корневом **`.env`** можно задать **`HF_TOKEN`** (gated-модели; compose подставляет его в контейнеры) и **`USE_FAKE_EMBEDDINGS=true`**, если нужен старт без HF без правки YAML.

Проверка DNS:  
`docker compose run --rm backend poetry run python -c "import socket; print(socket.gethostbyname('huggingface.co'))"`.

Если корпоративная политика запрещает публичные DNS — удалите блоки **`dns:`** в compose и настройте DNS в **Docker Desktop → Settings → Docker Engine**, либо исключите Docker из VPN split-tunnel.

**Chroma**: версия образа **`chromadb/chroma`** должна соответствовать пакету **`chromadb`** в Poetry (сейчас **1.5.x**): старый сервер **0.5.x** отдаёт **404 на `/api/v2/auth/identity`** при клиенте **1.5.x**. После upgrade образа или смены размерности эмбеддингов удалите том **`chroma_data`** (`docker compose down` и при необходимости **`docker volume rm ...`**), если нужен чистый индекс.

Локально без Docker: **`USE_FAKE_EMBEDDINGS=false`**, интернет до HF, при желании **`HF_HOME`** в `.env`.

### Сборка `docker compose --build` и VPN / таймауты

Во время сборки **`backend` / `worker`** Poetry качает пакеты с **PyPI** (`files.pythonhosted.org`), не только Docker Hub. Ошибки вида `Read timed out` на `nvidia-cusparse` означали, что ставился **PyTorch с CUDA** (очень тяжёлый).

В **`pyproject.toml`** задан явный источник **`pytorch-cpu`** (`download.pytorch.org/whl/cpu`) и зависимость **`torch`** от него, а в **`poetry.lock`** зафиксирован вариант **`2.11.0+cpu`** без цепочки **`nvidia-*`** с PyPI. В образе выполняется только **`poetry install`** по lock (без `poetry lock` в Dockerfile).

Если всё равно рвётся сеть — стабилизируй VPN или повтори `docker compose build --no-cache`. Для прод-GPU образ собирай отдельно (другой базовый слой / зависимости), сейчас образ ориентирован на **CPU** в контейнере.

## Local development with Poetry (кратко)

```powershell
cd c:\ChatBot_Ai\backend
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

## Chat ACL, алерты

- **Прод:** `CHAT_ACL_DISABLED=false`, заголовок **`X-Chat-Signature`** (HMAC-SHA256 от `chat_id` с секретом `CHAT_ACL_SECRET`).
- **Локально:** в `.env.example` уже `CHAT_ACL_DISABLED=true` — можно вызывать `/api/v1/chat` без подписи.
- Опционально: **`ALERT_WEBHOOK_URL`** — webhook при необработанных исключениях API.
