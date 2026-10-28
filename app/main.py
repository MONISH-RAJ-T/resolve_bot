"""ResolveBot. Start with:  uvicorn app.main:app --port 8000   (or:  uvicorn main:app --port 8000)"""
from fastapi import FastAPI

from app.routes import chat

app = FastAPI(title="ResolveBot")
app.include_router(chat.router)
