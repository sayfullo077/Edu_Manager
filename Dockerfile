# syntax=docker/dockerfile:1
FROM python:3.13-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    DJANGO_SETTINGS_MODULE=config.settings.prod

COPY --from=ghcr.io/astral-sh/uv:0.8 /uv /usr/local/bin/uv
WORKDIR /app

# Bog'liqliklar alohida qatlamda — kod o'zgarganda qayta o'rnatilmaydi.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY . .
# collectstatic uchun vaqtinchalik qiymatlar (runtime'da haqiqiylari .env.prod'dan keladi)
RUN SECRET_KEY=build-only-$(head -c 48 /dev/urandom | base64) ALLOWED_HOSTS=build REDIS_URL=redis://build \
    FIELD_ENCRYPTION_KEYS=$(head -c 32 /dev/urandom | base64 | tr '+/' '-_') FIELD_INDEX_KEY=build \
    uv run --no-sync python manage.py collectstatic --noinput

# Root'siz ishlash: konteyner buzilsa ham tizimga ta'sir kamroq.
RUN useradd --system --uid 10001 app && mkdir -p /app/media /app/private_media && chown -R app /app/media /app/private_media
USER app

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8000/healthz/')"
CMD ["uv", "run", "--no-sync", "gunicorn", "config.wsgi:application", "-c", "deploy/gunicorn.conf.py"]
