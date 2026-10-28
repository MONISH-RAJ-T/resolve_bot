"""Shim so that `uvicorn main:app --port 8000` also works."""
from app.main import app  # noqa: F401
