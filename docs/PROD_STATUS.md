# Готовность к prod

Проверка: `backend/scripts/go-live-checklist.ps1`

## Стек

| Сервис | Ожидание |
|--------|----------|
| chatbot-backend | healthy, LLM ≠ rule_based |
| chatbot-worker | healthy |
| postgres, redis, chroma | up |
| telegram-bot | опционально; нужен `api.telegram.org` |

## Чеклист

- [x] KB проиндексирована
- [x] Активная LLM (gigachat)
- [x] FAQ (go-live)
- [x] Upload API → 401 без auth
- [x] `PUBLIC_SHOW_ADMIN_LINK=false`
- [x] `LLM_ALLOW_RULE_BASED_FALLBACK=false` (`init-env.ps1 -Prod`)
- [ ] Промпт RAG в `/admin`
- [ ] Telegram на целевой сети
- [ ] Prod-хост + TLS

## Деплой

```powershell
cd c:\ChatBot_Ai\backend
.\scripts\init-env.ps1 -Prod
cd c:\ChatBot_Ai
docker compose up -d --build
.\scripts\go-live-checklist.ps1 -AdminUsername admin -AdminPassword "<из .env>"
.\scripts\backup.ps1
```

Расписание бэкапов (Windows, от админа): `.\scripts\schedule-backup.ps1`
