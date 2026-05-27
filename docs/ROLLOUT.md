# Runbook: вывод ChatBot AI в prod



## 1. Подготовка `.env` (корень репозитория)



```powershell

cd c:\ChatBot_Ai\backend

.\scripts\init-env.ps1

```



Обязательно для prod:



```env

ADMIN_API_TOKEN=<длинный-случайный-токен>

ADMIN_USERNAME=admin

ADMIN_PASSWORD=<сильный-пароль>

ADMIN_SESSION_SECRET=<случайный-секрет>

LLM_SETTINGS_ENCRYPTION_KEY=<fernet-key>

LLM_ALLOW_RULE_BASED_FALLBACK=false

USE_FAKE_EMBEDDINGS=false

PUBLIC_SHOW_ADMIN_LINK=false

CHAT_ACL_DISABLED=true

TELEGRAM_BOT_TOKEN=<от BotFather>

```



`init-env.ps1` генерирует токены и пароль, если их нет в `.env`.



## 2. Запуск стека



```powershell

cd c:\ChatBot_Ai\backend

.\scripts\deploy.ps1            # docker compose up + smoke + go-live

# с Telegram:

.\scripts\deploy.ps1 -WithTelegram

```



Или вручную из **корня репозитория**:



```powershell

cd c:\ChatBot_Ai

docker compose up -d --build

docker compose --profile telegram up -d --build

docker compose ps

```



Compose читает `.env` из корня через `env_file: ../.env` в `backend/docker-compose.yml`.



Проверки:



- `GET http://localhost:8000/healthz` → `ok`

- `GET http://localhost:8000/readyz` → `ready`



> Холодный старт backend: дождаться `healthz` (до ~2 мин).



## 3. Наполнение базы знаний



1. Открыть `http://localhost:8000/admin`

2. Войти: **логин/пароль** из `.env` (`ADMIN_USERNAME` / `ADMIN_PASSWORD`)

3. Загрузить `kb.zip` или документы PDF/DOCX/TXT

4. Wait until status `indexed`



## 4. Настройка LLM



1. `/admin` → «Интеграции LLM» → создать `openai_compatible`

2. Указать model, base URL, API key

3. Активировать интеграцию + Test

4. В шапке админки — активный провайдер (не `rule_based`)

5. Перед деплоем: `init-env.ps1 -Prod`



## 5. Smoke и go-live



```powershell

cd c:\ChatBot_Ai\backend

# из .env автоматически (deploy.ps1) или вручную:

.\scripts\smoke.ps1 -AdminUsername admin -AdminPassword "<ADMIN_PASSWORD>"

.\scripts\go-live-checklist.ps1 -AdminUsername admin -AdminPassword "<ADMIN_PASSWORD>"

```



Вручную:



- Сайт `/` — вопрос по KB → ответ + источники

- Telegram — тот же вопрос → ответ + блок «Источники»

- `/reset` в Telegram — очистка истории



## 6. Ротация секретов



| Секрет | Действие |

|--------|----------|

| `ADMIN_PASSWORD` | Обновить в `.env` → `docker compose up -d --force-recreate backend` |

| `ADMIN_API_TOKEN` | Обновить в `.env` → `--force-recreate backend telegram-bot` |

| `TELEGRAM_BOT_TOKEN` | Обновить в `.env` → `--force-recreate telegram-bot` |

| LLM API key | Только через `/admin`, redeploy не нужен |



## 7. Бэкапы



```powershell

cd c:\ChatBot_Ai\backend

.\scripts\backup.ps1

```



## 8. Обновление KB



1. Загрузить новые файлы через `/admin`

2. Удалить устаревшие документы в админке

3. При смене embedding model — `POST /api/v1/admin/reindex` (Bearer token или cookie-сессия)



## 9. Чеклист «готово к людям»

См. актуальный статус: [docs/PROD_STATUS.md](PROD_STATUS.md)

- [ ] Документы `indexed` — `go-live-checklist.ps1`
- [ ] Активная LLM (не `rule_based`), fallback выключен (`init-env.ps1 -Prod`)
- [ ] FAQ: восстановление доступа / пополнение — в go-live
- [ ] Промпт RAG настроен
- [ ] Сайт отвечает по KB
- [ ] Telegram (если нужен): `TELEGRAM_BOT_TOKEN` + доступ к `api.telegram.org`
- [ ] Upload API закрыт без admin auth
- [ ] Ссылка на админку скрыта (`PUBLIC_SHOW_ADMIN_LINK=false`)
- [ ] Секреты не в git
- [ ] Бэкап: `.\scripts\backup.ps1`

