"""Gunicorn config — auto-loaded from CWD by `gunicorn` with no -c flag.

This makes `gunicorn app:app` (Render's default) Just Work for an ASGI app:
it forces the uvicorn worker class so FastAPI runs correctly, sets a single
worker (in-process scheduler + bootstrap thread must run exactly once),
extends the timeout to accommodate first-boot model loading, and binds to
the platform-provided $PORT.
"""
import os

bind = f"0.0.0.0:{os.environ.get('PORT', '8000')}"
worker_class = "uvicorn.workers.UvicornWorker"
workers = 1
timeout = 600
keepalive = 5
graceful_timeout = 30
accesslog = "-"
errorlog = "-"
loglevel = os.environ.get("LOG_LEVEL", "info").lower()
