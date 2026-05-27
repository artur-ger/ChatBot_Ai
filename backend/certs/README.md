# CA для TLS GigaChat (Russian Trusted)

Источник: https://developers.sber.ru/docs/ru/gigachat/certificates

```powershell
curl.exe -fsSL "https://gu-st.ru/content/lending/russian_trusted_root_ca_pem.crt" -o backend/certs/russian_trusted_root_ca_pem.crt
curl.exe -fsSL "https://gu-st.ru/content/lending/russian_trusted_sub_ca_pem.crt" -o backend/certs/russian_trusted_sub_ca_pem.crt
docker compose up -d --build backend
```
