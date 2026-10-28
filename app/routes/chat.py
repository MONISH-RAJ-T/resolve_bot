"""POST /chat. HTTP errors used: 400 (bad body), 401 (bad customer), 403 (someone else's session).
Everything else - even 'order not found' - is a normal 200 reply."""
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from app.core.database import get_connection
from app.repositories import customer_repo
from app.services import chat_service
from app.services.session_service import session_owner

router = APIRouter()


def _error(status: int, text: str) -> JSONResponse:
    return JSONResponse({"error": text}, status_code=status)


def _customer_exists(customer_id: str) -> bool:
    with get_connection() as conn:
        return customer_repo.exists(conn, customer_id)


@router.post("/chat")
async def chat(request: Request):
    customer_id = (request.headers.get("X-Customer-Id") or "").strip()
    if not customer_id or not await run_in_threadpool(_customer_exists, customer_id):
        return _error(401, "Missing or unknown X-Customer-Id")

    try:
        body = await request.json()
    except Exception:
        return _error(400, "Body must be valid JSON")
    if not isinstance(body, dict):
        return _error(400, "Body must be a JSON object")
    session_id, message = body.get("session_id"), body.get("message")
    if isinstance(session_id, int) and not isinstance(session_id, bool):
        session_id = str(session_id)
    if not isinstance(session_id, str) or not session_id.strip() or not isinstance(message, str) or not message.strip():
        return _error(400, "session_id and message are required")

    owner = session_owner(session_id)
    if owner is not None and owner != customer_id:
        return _error(403, "This session belongs to another customer")
    try:
        reply = await run_in_threadpool(chat_service.handle, customer_id, session_id, message)
    except PermissionError:
        return _error(403, "This session belongs to another customer")
    return reply.model_dump()
