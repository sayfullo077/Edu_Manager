#!/bin/sh
# .env.prod yaratadi: barcha maxfiy kalitlar tasodifiy. Faqat domen yoki server IP so'raladi.
# Ishlatish (loyiha papkasida):  sh deploy/make-env.sh
set -e

ENV_FILE=".env.prod"
if [ -f "$ENV_FILE" ]; then
    echo "XATO: $ENV_FILE allaqachon bor. Ustiga yozilmaydi (shifrlash kaliti yo'qolsa ma'lumot qaytmaydi!)."
    echo "Yangidan yaratish kerak bo'lsa, avval eskisini zaxiralang va o'chiring."
    exit 1
fi
command -v openssl >/dev/null || { echo "openssl kerak: apt install -y openssl"; exit 1; }

rand() { openssl rand -base64 "$1" | tr -d '\n/+=' | cut -c1-"$2"; }

printf "Domen (masalan maktab.uz). Domen yo'q bo'lsa — bo'sh qoldiring (IP bilan sinov rejimi): "
read -r DOMAIN

if [ -n "$DOMAIN" ]; then
    HOSTS="$DOMAIN,127.0.0.1,localhost"
    ORIGINS="https://$DOMAIN"
    HTTPS="true"
else
    printf "Serverning ochiq IP manzili (Contabo panelidagi IPv4): "
    read -r SERVER_IP
    [ -n "$SERVER_IP" ] || { echo "IP kiritilmadi."; exit 1; }
    HOSTS="$SERVER_IP,127.0.0.1,localhost"
    ORIGINS="http://$SERVER_IP"
    HTTPS="false"
fi

umask 077
cat > "$ENV_FILE" <<EOF
# ===== Edu Manager — production sozlamalari ($(date +%Y-%m-%d)) =====
# DIQQAT: FIELD_ENCRYPTION_KEYS va FIELD_INDEX_KEY ni xavfsiz joyda zaxiralang.
# Ular yo'qolsa, shifrlangan pasport/JSHSHIR ma'lumotlari QAYTA TIKLANMAYDI.

SECRET_KEY=$(rand 96 64)
ALLOWED_HOSTS=$HOSTS
CSRF_TRUSTED_ORIGINS=$ORIGINS
DOMAIN=$DOMAIN

# HTTPS=false — faqat domensiz qisqa sinov (shifrsiz HTTP!). Domen bilan: true.
HTTPS=$HTTPS
# nginx rejimi: http (sinov / sertifikat olish) -> sertifikat olingach https
NGINX_MODE=http

POSTGRES_PASSWORD=$(rand 32 32)
REDIS_PASSWORD=$(rand 32 32)

FIELD_ENCRYPTION_KEYS=$(openssl rand -base64 32 | tr '+/' '-_')
FIELD_INDEX_KEY=$(rand 48 48)

# Admin panel manzili (botlar /admin/ ni skanerlaydi)
ADMIN_URL=boshqaruv-$(rand 12 10)/

# Demo hisoblar paroli (seed_demo)
DEMO_PASSWORD=Demo-$(rand 16 12)

LOGIN_DEFAULT_METHOD=password
GUNICORN_WORKERS=3

# SMS/Telegram hali ulanmagan: kodlar faqat konteyner logida ko'rinadi. Parol bilan kiring.
# TELEGRAM_BOT_TOKEN=
# TELEGRAM_BOT_USERNAME=
EOF

echo ""
echo "Tayyor: $ENV_FILE yaratildi (faqat siz o'qiy olasiz)."
echo "Demo parol:  grep DEMO_PASSWORD $ENV_FILE"
echo "Admin manzili: grep ADMIN_URL $ENV_FILE"
if [ "$HTTPS" = "false" ]; then
    echo "Rejim: IP bilan sinov (http://$SERVER_IP). Haqiqiy foydalanishga o'tishda domen ulang — docs/DEPLOY.md."
else
    echo "Rejim: domen ($DOMAIN). Avval DNS A-yozuvini server IP'siga yo'naltiring, so'ng sertifikat oling — docs/DEPLOY.md."
fi
