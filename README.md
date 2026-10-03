# Edu Manager

Xususiy maktab uchun boshqaruv platformasi: o'quvchilar, ota-onalar, shartnomalar, dars jadvali,
to'lovlar va kassa, o'qituvchilar oyligi, yotoqxona.

**Stek:** Python 3.13 · Django 6 · PostgreSQL · Redis · Django templates + vanilla JS · o'z CSS dizayn tizimi

## Imkoniyatlar (hozirgi holat)

- Ro'yxatdan o'tish yo'q — akkauntlarni administrator yaratadi
- Kirish: telefon + parol yoki bir martalik kod (SMS / Telegram bot)
- Rollar: O'qituvchi, Zavuch, Reception, Direktor — bitta foydalanuvchida bir nechta rol, paneldan almashtiriladi
- Yorug'/qorong'i mavzu, mobil moslashuv

## Ishga tushirish

```bash
uv sync
createdb edu_manager
uv run python manage.py migrate
uv run python manage.py seed_demo      # demo foydalanuvchilar → demo_credentials.txt
uv run python manage.py runserver 8000
```

Sozlamalar muhit o'zgaruvchilari yoki `.env` fayli orqali beriladi (asosiylari):

| O'zgaruvchi | Tavsif |
|---|---|
| `DATABASE_URL` | `postgres://user:pass@localhost:5432/edu_manager` |
| `REDIS_URL` | `redis://localhost:6379/1` (production'da majburiy) |
| `SECRET_KEY`, `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS` | production uchun majburiy |
| `ADMIN_URL` | admin panel manzili (production'da tasodifiy qiling) |
| `TRUSTED_PROXY_COUNT` | nginx ortida `1`, Cloudflare + nginx ortida `2` |
| `TELEGRAM_BOT_TOKEN`, `TELEGRAM_BOT_USERNAME`, `TELEGRAM_WEBHOOK_SECRET` | Telegram orqali kod yuborish |
| `LOGIN_DEFAULT_METHOD` | `password` yoki `code` |

Dev rejimida SMS va Telegram kodlari server terminaliga chiqadi.

## Testlar va sifat

```bash
uv run pytest
uv run ruff check .    # jumladan Bandit xavfsizlik qoidalari
```

## Hujjatlar

- [docs/PLAN.md](docs/PLAN.md) — arxitektura, ma'lumotlar modeli, bosqichlar
- [docs/SECURITY.md](docs/SECURITY.md) — xavfsizlik, DDoS himoyasi, production tekshiruv ro'yxati

## Production

To'liq yo'riqnoma (Contabo/Ubuntu, IP bilan sinov yoki domen + HTTPS, cron, zaxira): [docs/DEPLOY.md](docs/DEPLOY.md).

```bash
sh deploy/make-env.sh                                                   # .env.prod (tasodifiy kalitlar)
docker compose -f docker-compose.prod.yml --env-file .env.prod up -d --build
```
