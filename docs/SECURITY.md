# Xavfsizlik va unumdorlik

Himoya bir necha qatlamda quriladi: biri o'tkazib yuborsa, keyingisi ushlaydi.

```
Internet → [Cloudflare] → nginx → gunicorn → Django middleware → servislar → PostgreSQL/Redis
             L3/L4 DDoS    L7 rate limit   timeout   global limit     use-case limitlari
```

## 1. DDoS va ortiqcha yuk

| Qatlam | Nima qiladi | Qayerda |
|---|---|---|
| **Cloudflare** (tavsiya) | Volumetrik (L3/L4) hujumlar, bot filtr, WAF. Serverning haqiqiy IP'si yashiriladi | Domen DNS sozlamasi |
| **nginx** | IP bo'yicha 20 so'rov/s (burst 40), `/login/` uchun 10/daqiqa, 30 ta parallel ulanish; slowloris'ga qarshi timeout'lar; katta so'rov tanasi (>5 MB) rad etiladi; faqat GET/HEAD/POST | `deploy/nginx.conf` |
| **gunicorn** | 30 s timeout, so'rov qatori/sarlavha hajmi limiti, xotira sizishiga qarshi worker qayta ishga tushishi | `deploy/gunicorn.conf.py` |
| **Django** | Har bir IP'ga daqiqasiga 300 so'rov (Redis, barcha workerlar uchun umumiy) → 429 | `apps/common/middleware.py` |
| **PostgreSQL** | `statement_timeout` 15 s — og'ir so'rov bazani bloklamaydi | `DB_STATEMENT_TIMEOUT_MS` |
| **Redis** | `maxmemory 256mb` + LRU — xotira tugab qolmaydi | `docker-compose.prod.yml` |

> Ilova darajasidagi hech qanday kod volumetrik DDoS'ni to'xtata olmaydi — trafik serverga yetib kelishining o'zi
> kanalni to'ldiradi. Shuning uchun production'da **Cloudflare (bepul tarif ham yetadi)** qat'iy tavsiya etiladi.

## 2. Kirish (autentifikatsiya) hujumlari

| Hujum | Himoya | Limit (`settings.RATE_LIMITS`) |
|---|---|---|
| SMS bombing (SMS pulini sarflash) | IP va telefon bo'yicha kod so'rash limiti, 60 s qayta yuborish oralig'i | IP: 10/10 daqiqa · raqam: 5/soat |
| OTP kodni terib topish | Har kodga 5 urinish, 3 daqiqa muddat, IP limiti, bir vaqtda faqat 1 ta amaldagi kod | IP: 30/10 daqiqa |
| Parol brute-force | IP limiti (faqat xato urinishlar sanaladi) | 20/15 daqiqa |
| Credential stuffing (ko'p IP'dan bitta akkaunt) | Akkaunt bo'yicha limit | 10/15 daqiqa |
| Race condition (parallel so'rovlar) | `select_for_update` + atomar Redis hisoblagichlari | — |
| User enumeration | Raqam yo'q / Telegram ulanmagan bo'lsa ham javob bir xil | — |
| Admin panelga brute-force | Admin o'z login formasini ishlatmaydi → bizning limitli loginga yo'naltiriladi; `ADMIN_URL` o'zgartiriladi | — |
| Telegram akkaunt egallash | `contact.user_id == from.id` tekshiruvi; webhook secret (URL + sarlavha, constant-time) | — |
| Open redirect (`?next=`) | `url_has_allowed_host_and_scheme` | — |

Parollar **Argon2** bilan xeshlanadi. OTP kodlar bazada ochiq saqlanmaydi (HMAC), taqqoslash constant-time.

## 3. Veb zaifliklar

- **XSS**: Django avtoescape + qat'iy **CSP** (`script-src 'self' 'nonce-…'`) — XSS topilsa ham begona skript ishlamaydi.
  Inline `style=""` atributlari taqiqlangan → CSS klasslar ishlatiladi. Inline `<script>`/`<style>` faqat `nonce="{{ csp_nonce }}"` bilan.
- **CSRF**: Django CSRF + `SameSite=Lax` cookie'lar. Webhook yagona `csrf_exempt` (secret bilan himoyalangan).
- **Clickjacking**: `X-Frame-Options: DENY` + `frame-ancestors 'none'`.
- **Cookie**: `HttpOnly`, `Secure`, `__Host-` prefiksi (prod), sessiya login'da yangilanadi.
- **HTTPS**: HSTS 1 yil + preload, HTTP → HTTPS.
- **Injection**: faqat ORM; `brand_color` qat'iy HEX validatsiya (`<style>` ichiga yoziladi).
- **Maxfiy ma'lumotlar**: parol maydoni xato hisobotlariga tushmaydi (`sensitive_post_parameters`),
  shaxsiy sahifalar `Cache-Control: no-store`, `robots.txt` indekslashni taqiqlaydi.
- **Supply chain**: tashqi CDN skriptlari yo'q (faqat Google Fonts CSS/shrift).

## 4. Unumdorlik va masshtablash

- **Redis**: rate limit, sessiyalar (`cached_db`), maktab sozlamalari keshi. Stateless worker'lar → gorizontal masshtablash mumkin.
- **DB**: psycopg3 connection pool (prod), `CONN_HEALTH_CHECKS`, indekslar, `select_related`.
- **Lazy yuklash**: rol va maktab sozlamalari faqat shablon so'raganda olinadi (static/webhook so'rovlari bazaga bormaydi).
- **Static**: WhiteNoise — gzip/brotli, hash'li nomlar, 1 yillik kesh.
- **Tozalash**: `manage.py purge_expired_codes` (cron, kuniga 1 marta).

## 5. Production tekshiruv ro'yxati

- [ ] `.env.prod`: `SECRET_KEY` (50+ belgi), `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, `REDIS_URL`, `ADMIN_URL` (tasodifiy), `POSTGRES_PASSWORD`, `REDIS_PASSWORD`
- [ ] `TRUSTED_PROXY_COUNT`: nginx → 1, Cloudflare + nginx → 2 (noto'g'ri qiymat rate limitni chetlab o'tishga imkon beradi!)
- [ ] `uv run python manage.py check --deploy` — 0 ogohlantirish
- [ ] Domen Cloudflare orqali, serverning 80/443 dan boshqa portlari yopiq (ufw)
- [ ] PostgreSQL va Redis tashqariga ochilmagan (faqat `backend` tarmog'i)
- [ ] Kunlik DB backup (`pg_dump`) + tiklashni sinash
- [ ] `security` logger'ini monitoring qilish (xato parollar, 429'lar)
- [ ] Bog'liqliklar zaifligini tekshirish: `uvx pip-audit` (oyiga bir marta)
