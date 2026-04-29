"""Top-level shim so `gunicorn app:app` (Render's default command) finds the
FastAPI application without needing a custom start command."""
from pradapicks.api import app  # noqa: F401
