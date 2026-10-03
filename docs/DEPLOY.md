# Deploy — Contabo (Ubuntu) serveriga MVP sinov uchun

Stek: **nginx → gunicorn (Django) → PostgreSQL + Redis**, hammasi Docker'da. Faqat nginx (80/443) tashqariga ochiq.
Ikki rejim:

| Rejim | Qachon | Manzil |
|---|---|---|
| **A. IP bilan sinov** (`HTTPS=false`) | Domen hali yo'q, tez ko'rish uchun | `http://SERVER_IP` — **shifrsiz**, faqat qisqa sinov, haqiqiy ma'lumot kiritmang |
| **B. Domen + HTTPS** (`HTTPS=true`) | Haqiqiy foydalanish | `https://maktab.uz` — Let's Encrypt bepul sertifikati |

---

## 0. Kompyuteringizda: kodni GitHub'ga yuborish

```bash
git add -A
git commit -m "MVP: deploy tayyorlandi"
git push origin main
```

> Repozitoriy **Private** bo'lsin (GitHub → Settings → General → Danger Zone → Change visibility).
> `.env*`, `demo_credentials.txt`, `reference/` (skrinshotlar) git'ga tushmaydi — `.gitignore`da.

## 1. Serverga kirish va tayyorlash (bir marta)

```bash
ssh root@SERVER_IP
```

> ⚠️ **Server bo'sh bo'lmasa** (boshqa saytlar/xizmatlar ishlayapti): `apt upgrade` va `ufw enable`ni ko'r-ko'rona
> yurgizmang — `ufw` faqat 22/80/443 ni qoldirib, boshqa xizmatlar portini yopib qo'yadi. Avval:
> `ufw status` va `ss -ltnp` bilan qaysi portlar ishlatilayotganini ko'ring. Docker bor bo'lsa (`docker --version`),
> o'rnatish qatorini o'tkazib yuboring.

```bash
apt update && apt upgrade -y
apt install -y git openssl ufw
curl -fsSL https://get.docker.com | sh                 # Docker + compose (rasmiy skript)
ufw allow OpenSSH && ufw allow 80/tcp && ufw allow 443/tcp && ufw --force enable
```

Swap (RAM 4–8 GB bo'lsa ham build vaqtida foydali):

```bash
fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile
echo '/swapfile none swap sw 0 0' >> /etc/fstab
```

## 2. Kodni yuklab olish

```bash
mkdir -p /opt && cd /opt
git clone https://github.com/sayfullo077/Edu_Manager.git edu
cd /opt/edu
```

Private repo bo'lsa, parol o'rniga GitHub **Personal access token** so'raladi
(GitHub → Settings → Developer settings → Fine-grained tokens → faqat shu repo, `Contents: Read`).

## 3. Sozlamalar (`.env.prod`) — avtomatik

```bash
sh deploy/make-env.sh
```

Skript domenni so'raydi (bo'sh qoldirsangiz — server IP'sini) va **barcha maxfiy kalitlarni tasodifiy yaratadi**.

> ⚠️ **`.env.prod` ichidagi `FIELD_ENCRYPTION_KEYS` va `FIELD_INDEX_KEY`ni darhol xavfsiz joyga (parol menejeri)
> nusxalang.** Ular yo'qolsa, shifrlangan pasport/JSHSHIR ma'lumotlari qayta tiklanmaydi.

## 4. Ishga tushirish

```bash
docker compose -f docker-compose.prod.yml --env-file .env.prod up -d --build
```

Birinchi build 3–6 daqiqa. Migratsiyalar avtomatik bajariladi. Holat:

```bash
docker compose -f docker-compose.prod.yml --env-file .env.prod ps
curl -s http://127.0.0.1/healthz/          # → ok
```

**A rejim (IP):** brauzerda `http://SERVER_IP` — tayyor. 5-qadamga o'ting.

**B rejim (domen):** avval domen DNS'ida **A yozuv → SERVER_IP** (tarqalishi 5–30 daqiqa), keyin sertifikat:

```bash
. ./.env.prod
docker compose -f docker-compose.prod.yml --env-file .env.prod run --rm certbot \
  certonly --webroot -w /var/www/certbot -d "$DOMAIN" --email SIZNING@EMAIL.uz --agree-tos --no-eff-email
sed -i 's/^NGINX_MODE=http$/NGINX_MODE=https/' .env.prod
docker compose -f docker-compose.prod.yml --env-file .env.prod up -d nginx
```

Endi `https://DOMEN` ishlaydi, `http` avtomatik `https`ga o'tadi.

## 4-B. Serverda nginx ALLAQACHON bor bo'lsa (boshqa saytlar bilan) — `edu.it-services.uz`

Tekshirish: `ss -ltnp | grep -E ':80 |:443 '` — `nginx` chiqsa, 80/443 band. Bu holda bizning nginx konteyneri
ishlatilmaydi (boshqa saytlar to'xtab qolmasin): ilova `127.0.0.1:8001`da, tizim nginx'i unga uzatadi.

```bash
cd /opt/edu
sh deploy/make-env.sh                       # domen: edu.it-services.uz
mkdir -p media && chown 10001:10001 media   # yuklangan fayllar (ilova foydalanuvchisi)
docker compose -f docker-compose.prod.yml -f docker-compose.hostnginx.yml --env-file .env.prod up -d --build
curl -s http://127.0.0.1:8001/healthz/      # → ok
```

Tizim nginx'iga sayt qo'shish (boshqa saytlarga tegmaydi; xato bo'lsa — qayta yuklanmaydi):

```bash
cp deploy/host-nginx/edu-proxy.conf /etc/nginx/snippets/edu-proxy.conf
cp deploy/host-nginx/edu.conf /etc/nginx/sites-available/edu.it-services.uz.conf
ln -s /etc/nginx/sites-available/edu.it-services.uz.conf /etc/nginx/sites-enabled/
nginx -t && systemctl reload nginx
```

HTTPS sertifikati (certbot nginx sayt faylini o'zi yangilaydi, avtomatik yangilanish ham o'rnatiladi):

```bash
apt install -y certbot python3-certbot-nginx
certbot --nginx -d edu.it-services.uz --redirect -m SIZNING@EMAIL.uz --agree-tos --no-eff-email
```

Tayyor: **https://edu.it-services.uz**. Bu rejimda keyingi barcha `docker compose` buyruqlariga
`-f docker-compose.prod.yml -f docker-compose.hostnginx.yml` qo'shiladi (6-qadamdagi sertifikat cron'i kerak emas —
certbot o'zi yangilaydi).

## 5. Demo ma'lumotlar va kirish

```bash
docker compose -f docker-compose.prod.yml --env-file .env.prod exec web python manage.py seed_demo
grep DEMO_PASSWORD .env.prod
```

Demo hisoblar (parol — `DEMO_PASSWORD`): `90 000 00 01` (o'qituvchi + zavuch + reception), `90 000 00 03` (zavuch),
`90 000 00 04` (reception), `90 000 00 05` (direktor), `90 000 00 00` (superadmin).

O'zingizning superadmin hisobingiz:

```bash
docker compose -f docker-compose.prod.yml --env-file .env.prod exec web python manage.py createsuperuser
```

Admin panel: `https://DOMEN/<ADMIN_URL>` (`grep ADMIN_URL .env.prod`).

> ⚠️ Demo hisoblar (jumladan **superadmin `90 000 00 00`**) bitta umumiy demo parolga ega — server internetga ochiq.
> Sinovni tugatgach, haqiqiy foydalanishga o'tishda **demo ma'lumotsiz toza baza** bilan boshlang
> (pastda «Noldan qayta boshlash») va faqat `createsuperuser` bilan o'z hisobingizni yarating.

## 6. Muntazam vazifalar (cron) va zaxira nusxa

```bash
mkdir -p /opt/backups && crontab -e
```

Qo'shing:

```cron
# Har kuni 01:00 — oylik to'lov grafiklari (yangi oy boshlanganda yaratadi; idempotent)
0 1 * * * cd /opt/edu && docker compose -f docker-compose.prod.yml --env-file .env.prod exec -T web python manage.py generate_monthly_invoices >> /var/log/edu-cron.log 2>&1
# Har kuni 03:00 — eskirgan bir martalik kodlarni tozalash
0 3 * * * cd /opt/edu && docker compose -f docker-compose.prod.yml --env-file .env.prod exec -T web python manage.py purge_expired_codes >> /var/log/edu-cron.log 2>&1
# Har kuni 02:00 — PostgreSQL zaxira nusxasi (14 kun saqlanadi)
0 2 * * * cd /opt/edu && docker compose -f docker-compose.prod.yml --env-file .env.prod exec -T db pg_dump -U edu -Fc edu_manager > /opt/backups/edu-$(date +\%F).dump && find /opt/backups -name 'edu-*.dump' -mtime +14 -delete
# Har dushanba 04:00 — sertifikatni yangilash (faqat B rejim)
0 4 * * 1 cd /opt/edu && docker compose -f docker-compose.prod.yml --env-file .env.prod run --rm certbot renew --webroot -w /var/www/certbot && docker compose -f docker-compose.prod.yml --env-file .env.prod exec -T nginx nginx -s reload
```

> Zaxira nusxani **serverdan tashqariga** ham ko'chirib turing (masalan, haftada bir `scp` bilan kompyuteringizga).
> Server yo'qolsa — faqat tashqaridagi nusxa qutqaradi. Nusxa + `.env.prod` birga saqlansin.

Zaxiradan tiklash:

```bash
docker compose -f docker-compose.prod.yml --env-file .env.prod exec -T db pg_restore -U edu -d edu_manager --clean --if-exists < /opt/backups/edu-YYYY-MM-DD.dump
```

## 7. Yangilash (yangi versiyani chiqarish)

```bash
cd /opt/edu
git pull
docker compose -f docker-compose.prod.yml --env-file .env.prod up -d --build
```

Migratsiyalar avtomatik. Yangilashdan oldin zaxira oling (6-qadamdagi `pg_dump` qatorini qo'lda yurgizing).

## 8. Kuzatish va muammolar

```bash
docker compose -f docker-compose.prod.yml --env-file .env.prod logs -f web       # ilova xatolari
docker compose -f docker-compose.prod.yml --env-file .env.prod logs -f nginx     # so'rovlar, 429/404
docker compose -f docker-compose.prod.yml --env-file .env.prod restart web
```

| Belgi | Sabab va yechim |
|---|---|
| `400 Bad Request` | Manzil `ALLOWED_HOSTS`da yo'q → `.env.prod`ni tuzating, `up -d web` |
| Login sahifasi qayta-qayta ochiladi | A rejimda `HTTPS=true` qolgan yoki B rejimda https'siz kirilyapti |
| `403 CSRF` | `CSRF_TRUSTED_ORIGINS` aniq manzil bilan (`http://IP` yoki `https://domen`) |
| `502 Bad Gateway` | `web` ishga tushmagan → `logs web` |
| `429 Too Many Requests` | nginx himoyasi (login: 10/daqiqa) — normal |

Noldan qayta boshlash (**BARCHA ma'lumot o'chadi**):

```bash
docker compose -f docker-compose.prod.yml --env-file .env.prod down -v
docker compose -f docker-compose.prod.yml --env-file .env.prod up -d --build
```

## 9. Hozircha yo'q (MVP cheklovlari)

- **SMS / Telegram kod** ulanmagan — parol bilan kiriladi (kodlar faqat `logs web`da ko'rinadi).
- **Onlayn to'lov** (Click/Payme) yo'q.
- Shaxsiy ma'lumotlar qonuni: O'zbekiston fuqarolarining shaxsiy ma'lumotlari O'zbekistondagi serverda saqlanishi
  talab qilinadi (PLAN.md, 2-bo'lim). Contabo — sinov uchun; haqiqiy o'quvchilar ma'lumoti bilan ishlashdan oldin
  yurist bilan aniqlang.
