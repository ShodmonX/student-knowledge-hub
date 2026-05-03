# Student Knowledge Hub Backend

[![CI](https://github.com/ShodmonX/student-knowledge-hub/actions/workflows/ci.yml/badge.svg)](https://github.com/ShodmonX/student-knowledge-hub/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/ShodmonX/student-knowledge-hub/graph/badge.svg)](https://codecov.io/gh/ShodmonX/student-knowledge-hub)

FastAPI asosidagi backend API. Loyiha PostgreSQL, Redis, SQLAlchemy, Alembic, Docker Compose va JWT auth bilan ishlaydi.

## Stack

- Python 3.12
- FastAPI
- SQLAlchemy async + asyncpg
- PostgreSQL 16
- Redis 7
- Docker / Docker Compose
- pytest + coverage

## Loyiha tuzilmasi

```text
app/
  api/                  API router wiring
  bootstrap/            backup, seed va scheduler servislar
  core/                 config, security, cache, exception handling
  db/                   SQLAlchemy session/model registry
  modules/              feature modullar: auth, users, materials, admin, telegram
  shared/               umumiy dependency/schema/service kodlari
scripts/                seed va backup worker entrypointlari
tests/                  pytest testlar
docker/entrypoint.sh    container startup script
```

## Muhim fayllar

- `.env.example` - barcha kerakli environment variable namunalari.
- `.dockerignore` - Docker image ichiga kirmasligi kerak bo'lgan local fayllar.
- `docker-compose.yml` - development compose.
- `docker-compose.prod.yml` - production compose.
- `docker-compose.net.yml` - API service’ni external nginx networkga ulash uchun overlay.
- `PRODUCTION_CHANGE_REPORT.md` - frontend/integratsiya uchun API behavior va production o'zgarishlari.

## Local ishga tushirish

1. `.env` yarating:

```bash
cp .env.example .env
```

2. `.env` ichida kamida quyidagilarni local muhitga moslang:

```env
APP_ENV=development
DEBUG=true
POSTGRES_DB=student_knowledge_hub
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres
DB_URL=postgresql+asyncpg://postgres:postgres@postgres:5432/student_knowledge_hub
REDIS_PASSWORD=dev-redis-password
REDIS_URL=redis://:dev-redis-password@redis:6379/0
JWT_SECRET_KEY=change-me-local-only
```

3. Agar `docker-compose.net.yml` bilan ishlatsangiz, external network mavjud bo'lishi kerak:

```bash
docker network create web
```

Network oldindan mavjud bo'lsa, bu command xato berishi mumkin; bunday holatda davom etish mumkin.

4. Development compose:

```bash
docker compose -f docker-compose.yml -f docker-compose.net.yml up --build
```

Makefile shortcutlari:

```bash
make ub   # build + up
make u    # up
make d    # down
make dv   # down -v
```

API default URL:

```text
http://localhost:8000
```

Healthcheck:

```text
GET /health/ready
```

## Production ishga tushirish

Production compose’da Redis tashqi portga ochilmaydi. API service host port publish qilmaydi; tashqi trafik nginx container orqali `docker-compose.net.yml` dagi external `web` networkdan keladi.

Production uchun `.env` qiymatlarini real secretlar bilan to'ldiring:

```env
APP_ENV=production
DEBUG=false
POSTGRES_DB=student_knowledge_hub
POSTGRES_USER=student_knowledge_hub
POSTGRES_PASSWORD=<strong-db-password>
DB_URL=postgresql+asyncpg://student_knowledge_hub:<strong-db-password>@postgres:5432/student_knowledge_hub
REDIS_PASSWORD=<strong-redis-password>
REDIS_URL=redis://:<strong-redis-password>@redis:6379/0
JWT_SECRET_KEY=<long-random-secret>
CORS_ORIGINS=https://your-frontend.example.com
ADMIN_EMAIL=<admin-email>
ADMIN_PASSWORD=<strong-admin-password>
BACKEND_SERVICE_NAME=backend-api
BOT_SERVICE_NAME=telegram-bot
INTERNAL_AUTH_SECRET=<long-random-secret>
INTERNAL_AUTH_TTL_SECONDS=300
TELEGRAM_EVENT_PUSH_ENABLED=true
BOT_INTERNAL_BASE_URL=http://telegram-bot:8000
BOT_INTERNAL_EVENT_PATH=/internal/events
TELEGRAM_EVENT_POLL_SECONDS=10
TELEGRAM_EVENT_BATCH_SIZE=50
TELEGRAM_EVENT_MAX_ATTEMPTS=5
MAIL_ENABLED=true
MAIL_HOST=sandbox.smtp.mailtrap.io
MAIL_PORT=2525
MAIL_API_TOKEN=<mailtrap-api-token>
MAIL_API_URL=https://send.api.mailtrap.io/api/send
MAIL_FROM_EMAIL=no-reply@your-domain.example
MAIL_FROM_NAME=Student Knowledge Hub
EMAIL_OUTBOX_MAX_ATTEMPTS=5
EMAIL_OUTBOX_RETRY_BASE_SECONDS=60
```

Production start:

```bash
docker compose -f docker-compose.prod.yml -f docker-compose.net.yml up -d --build
```

Faqat API container rebuild/restart:

```bash
docker compose -f docker-compose.prod.yml -f docker-compose.net.yml up -d --build api
```

## Environment variables

Asosiy variablelar:

| Variable | Required | Default | Izoh |
|---|---:|---|---|
| `APP_ENV` | Ha | `development` | `development` yoki `production` |
| `DEBUG` | Ha | `false` | Production’da `false` bo'lishi kerak |
| `DB_URL` | Ha | sqlite fallback | Async SQLAlchemy database URL |
| `POSTGRES_DB` | Prod ha | `student_knowledge_hub` | Postgres database nomi |
| `POSTGRES_USER` | Prod ha | `postgres` dev | Postgres user |
| `POSTGRES_PASSWORD` | Prod ha | `postgres` dev | Postgres password |
| `REDIS_PASSWORD` | Prod ha | `None` | Redis server paroli; production compose Redis’ni shu parol bilan ishga tushiradi |
| `REDIS_URL` | Prod ha | `None` | Rate limit, cache va token revocation uchun parolli Redis URL |
| `JWT_SECRET_KEY` | Prod ha | `change-me` | Production’da kuchli random secret bo'lishi shart |
| `CORS_ORIGINS` | Prod ha | localhostlar | Vergul bilan ajratilgan frontend originlar |
| `BACKEND_SERVICE_NAME` | Telegram integration uchun ha | `backend-api` | Backend bot service’ga request yuborganda ishlatiladigan service nomi |
| `BOT_SERVICE_NAME` | Telegram integration uchun ha | `telegram-bot` | Backend internal endpointlariga keladigan bot service nomi |
| `INTERNAL_AUTH_SECRET` | Telegram integration uchun ha | `None` | Bot va backend orasidagi umumiy HMAC secret |
| `INTERNAL_AUTH_TTL_SECONDS` | Yo'q | `300` | Internal request signature TTL |
| `BOT_INTERNAL_BASE_URL` | Push yoqilganda ha | `None` | Backend eventlarni push qiladigan bot service URL |
| `BOT_INTERNAL_EVENT_PATH` | Yo'q | `/internal/events` | Backend -> bot event endpoint path |
| `BOT_INTERNAL_TIMEOUT_SECONDS` | Yo'q | `10` | Backend -> bot request timeout |
| `TELEGRAM_EVENT_POLL_SECONDS` | Yo'q | `10` | `telegram-worker` event outbox’ni nechchi sekundda tekshirishi |
| `TELEGRAM_EVENT_BATCH_SIZE` | Yo'q | `50` | Bir worker siklida jo‘natiladigan maksimal Telegram event soni |
| `TELEGRAM_EVENT_MAX_ATTEMPTS` | Yo'q | `5` | Failed Telegram event qayta jo‘natish urinishlari limiti |
| `STORAGE_BACKEND` | Ha | `local` | `local` yoki `s3` |
| `BACKUP_LOCAL_ROOT` | Ha | `./backups` | Backup fayllar root papkasi |

Mailtrap/email:

| Variable | Required | Default | Izoh |
|---|---:|---|---|
| `MAIL_ENABLED` | Yo'q | `false` | `true` bo'lsa email outbox orqali yuborish navbatga qo'yiladi |
| `MAIL_HOST` | Email yoqilganda ha | `sandbox.smtp.mailtrap.io` | Mailtrap SMTP host |
| `MAIL_PORT` | Email yoqilganda ha | `2525` | Mailtrap SMTP port |
| `MAIL_USERNAME` | SMTP ishlatilsa ha | `None` | Mailtrap SMTP username |
| `MAIL_PASSWORD` | SMTP ishlatilsa ha | `None` | Mailtrap SMTP password |
| `MAIL_API_TOKEN` | API ishlatilsa ha | `None` | Mailtrap Email API token |
| `MAIL_API_URL` | API ishlatilsa ha | `https://send.api.mailtrap.io/api/send` | Mailtrap Email API endpoint |
| `MAIL_FROM_EMAIL` | Email yoqilganda ha | `no-reply@studentknowledgehub.local` | Email jo'natuvchi manzil |
| `MAIL_FROM_NAME` | Yo'q | `Student Knowledge Hub` | Email jo'natuvchi nomi |
| `MAIL_STARTTLS` | Yo'q | `true` | SMTP STARTTLS yoqish/o'chirish |
| `MAIL_TIMEOUT_SECONDS` | Yo'q | `10` | SMTP timeout, sekund |
| `EMAIL_OUTBOX_POLL_SECONDS` | Yo'q | `10` | Email worker outbox’ni tekshirish intervali |
| `EMAIL_OUTBOX_BATCH_SIZE` | Yo'q | `10` | Worker bir siklda yuboradigan email soni |
| `EMAIL_OUTBOX_MAX_ATTEMPTS` | Yo'q | `5` | Email yuborish maksimal urinishlari |
| `EMAIL_OUTBOX_RETRY_BASE_SECONDS` | Yo'q | `60` | Retry exponential backoff bazasi |
| `EMAIL_VERIFICATION_TOKEN_EXPIRE_HOURS` | Yo'q | `24` | Email verification token muddati |
| `PASSWORD_RESET_URL_PATH` | Yo'q | `/reset-password` | Frontend reset sahifasi path'i |
| `EMAIL_VERIFICATION_URL_PATH` | Yo'q | `/verify-email` | Frontend email verification sahifasi path'i |

DB pool/timeout:

| Variable | Default | Izoh |
|---|---:|---|
| `DB_POOL_SIZE` | `10` | SQLAlchemy pool size |
| `DB_MAX_OVERFLOW` | `20` | Qo'shimcha connection limiti |
| `DB_POOL_TIMEOUT` | `30` | Pool kutish vaqti, sekund |
| `DB_POOL_RECYCLE` | `1800` | Connection recycle, sekund |
| `DB_POOL_PRE_PING` | `true` | Eski connectionlarni tekshirish |
| `DB_STATEMENT_TIMEOUT_MS` | `30000` | asyncpg statement timeout |

Rate limit va lockout:

| Variable | Default |
|---|---:|
| `RATE_LIMIT_ENABLED` | `true` |
| `RATE_LIMIT_KEY_PREFIX` | `skh` |
| `RATE_LIMIT_LOGIN_MAX_REQUESTS` | `10` |
| `RATE_LIMIT_LOGIN_WINDOW_SECONDS` | `60` |
| `RATE_LIMIT_REGISTER_MAX_REQUESTS` | `5` |
| `RATE_LIMIT_REGISTER_WINDOW_SECONDS` | `300` |
| `RATE_LIMIT_PASSWORD_RESET_REQUEST_MAX_REQUESTS` | `5` |
| `RATE_LIMIT_PASSWORD_RESET_REQUEST_WINDOW_SECONDS` | `3600` |
| `RATE_LIMIT_PASSWORD_RESET_CONFIRM_MAX_REQUESTS` | `10` |
| `RATE_LIMIT_PASSWORD_RESET_CONFIRM_WINDOW_SECONDS` | `300` |
| `RATE_LIMIT_REFRESH_MAX_REQUESTS` | `30` |
| `RATE_LIMIT_REFRESH_WINDOW_SECONDS` | `60` |
| `RATE_LIMIT_SENSITIVE_MAX_REQUESTS` | `20` |
| `RATE_LIMIT_SENSITIVE_WINDOW_SECONDS` | `60` |
| `LOGIN_LOCKOUT_MAX_ATTEMPTS` | `5` |
| `LOGIN_LOCKOUT_WINDOW_SECONDS` | `900` |
| `LOGIN_LOCKOUT_SECONDS` | `900` |
| `ACCESS_TOKEN_REVOCATION_ENABLED` | `true` |

## Security behavior

### Rate limiting

Sensitive auth endpointlar Redis asosida rate-limited:

- `POST /api/v1/auth/register`
- `POST /api/v1/auth/login`
- `POST /api/v1/auth/refresh`
- `POST /api/v1/auth/forgot-password`
- `POST /api/v1/auth/reset-password`
- `POST /api/v1/auth/verify-email`
- `POST /api/v1/auth/resend-verification`
- `POST /api/v1/auth/logout`
- `GET /api/v1/auth/sessions`
- `DELETE /api/v1/auth/sessions/{session_id}`
- `POST /api/v1/auth/logout-all`
- Telegram link/verification endpointlari

Rate limit response:

```json
{
  "error_code": "rate_limit_exceeded",
  "message": "Too many requests",
  "details": {
    "scope": "auth.login",
    "retry_after_seconds": 60
  }
}
```

### Brute-force lockout

Login urinishlari Redis keylari orqali kuzatiladi:

- `skh:bf:login:fail:{sha256(ip|email)}`
- `skh:bf:login:lock:{sha256(ip|email)}`

Lockout response:

```json
{
  "error_code": "rate_limit_exceeded",
  "message": "Too many failed login attempts",
  "details": {
    "scope": "auth.login.lockout",
    "retry_after_seconds": 900
  }
}
```

### Access token revocation

Logout yoki logout-all paytida access token Redis’da TTL bilan blacklist qilinadi:

```text
skh:auth:revoked_access:{jti}
```

Protected endpointlar token revoked emasligini tekshiradi. Disabled user enforcement ataylab o'zgartirilmagan.

## Backup va restore

Manual backup endpoint:

```text
POST /api/v1/admin/backups
```

Restore API default holatda o'chirilgan. Bu loyiha restore’ni ishlab turgan database ustiga API orqali qilish uchun emas, DB tasodifan yo'qolganda operator tomonidan qo'lda tiklash uchun ishlatadi.

Qo'lda restore:

```bash
docker compose -f docker-compose.prod.yml run --rm backup \
  python scripts/manual_restore_backup.py <backup_id> --confirmation RESTORE:<backup_id>
```

Restore API faqat maxsus zarurat bo'lsa `BACKUP_RESTORE_API_ENABLED=true` bilan yoqiladi:

```text
POST /api/v1/admin/backups/{backup_id}/restore
```

Restore request body majburiy:

```json
{
  "confirmation": "RESTORE:<backup_id>"
}
```

Restore himoyalari:

- backup id validation
- `.dump` format validation
- allowed local backup root
- max restore size: `BACKUP_MAX_RESTORE_SIZE_BYTES`
- checksum verification
- offsite key prefix validation
- local path va offsite keylarni API response’da maskalash
- Postgres 16 bilan moslik uchun `transaction_timeout` restore fallback

Backup worker production’da `backup` service sifatida ishlaydi. Jadval:

```env
BACKUP_SCHEDULE_ENABLED=true
BACKUP_INTERVAL_SECONDS=86400
BACKUP_RUN_ON_START=true
```

Seed production start paytida avtomatik ishlamaydi (`RUN_SEED_ON_START=false`). Kerak bo'lsa qo'lda ishga tushiring:

```bash
docker compose -f docker-compose.prod.yml run --rm api python scripts/seed_once.py
```

## Testlar

Testlar Python venv orqali ishlatiladi. Development compose Postgres’ni hostda `127.0.0.1:5433`, Redis’ni `127.0.0.1:6380` ga chiqaradi.

Test runner default holatda alohida `student_knowledge_hub_test` database yaratadi va test sessiyasi tugagach o'chiradi. Xavfsizlik uchun test database nomi `test_` bilan boshlanishi yoki `_test` bilan tugashi shart.

1. Test dependency servislarini ishga tushiring:

```bash
docker compose up -d postgres redis
```

2. Full test + coverage:

```bash
venv/bin/python -m pytest --cov=app --cov-report=term-missing --cov-fail-under=90
```

Oxirgi tekshiruv natijasi:

```text
113 passed
coverage: 90.19%
```

Agar boshqa test database ishlatmoqchi bo'lsangiz, nomi test DB ekanini bildirishi kerak:

```bash
TEST_DATABASE_URL=postgresql+asyncpg://user:pass@127.0.0.1:5432/my_app_test \
venv/bin/python -m pytest
```

## API changelog

Frontend va integration behavior o'zgarishlari alohida hujjatda:

```text
PRODUCTION_CHANGE_REPORT.md
```

U yerda email outbox, token hash, admin guard, Redis auth, restore/seed jarayoni va frontend tekshirishi kerak bo'lgan API contract yozilgan.

## Docker image hygiene

`.dockerignore` image ichiga quyidagilar tushmasligini ta'minlaydi:

- `.git`
- `.env`
- virtualenv papkalari
- Python cache/test cache
- local DB/cache/log fayllari
- local storage/backups
- IDE/editor va OS generated fayllar

Bu image hajmini kamaytiradi va secret/local state image ichiga kirib qolish xavfini pasaytiradi.
