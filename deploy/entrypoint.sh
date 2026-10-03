#!/bin/sh
# Konteyner ishga tushganda: ma'lumotlar bazasi sxemasini yangilaydi, keyin asosiy buyruqni bajaradi.
# RUN_MIGRATIONS=0 — o'tkazib yuborish (masalan, bot konteynerida).
set -e

if [ "${RUN_MIGRATIONS:-1}" = "1" ]; then
    echo "[entrypoint] migratsiyalar..."
    python manage.py migrate --noinput
fi

exec "$@"
