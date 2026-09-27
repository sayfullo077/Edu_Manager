"""Gunicorn (production WSGI server) sozlamalari."""

import multiprocessing
import os

bind = "0.0.0.0:8000"

# Worker soni: CPU × 2 + 1. gthread — I/O kutishda (DB, SMS API) bloklanmaslik uchun.
workers = int(os.environ.get("GUNICORN_WORKERS", multiprocessing.cpu_count() * 2 + 1))
worker_class = "gthread"
threads = int(os.environ.get("GUNICORN_THREADS", 4))

# Osilib qolgan so'rov workerni abadiy band qilmasin.
timeout = 30
graceful_timeout = 30
keepalive = 5

# Xotira sizib chiqishiga qarshi: har N so'rovdan keyin worker qayta ishga tushadi.
max_requests = 1000
max_requests_jitter = 100

# Katta/buzuq sarlavhali so'rovlarga qarshi.
limit_request_line = 4094
limit_request_fields = 100
limit_request_field_size = 8190

accesslog = "-"
errorlog = "-"
loglevel = "info"
forwarded_allow_ips = "*"  # faqat nginx orqali kiriladi (port tashqariga ochilmagan)
