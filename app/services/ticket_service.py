"""Tickets: tool 5 (create_support_ticket) for warranty and cancellation."""
import uuid
from datetime import datetime, timezone

from app.core.database import get_connection
from app.repositories import parameter_repo, ticket_repo
from app.rules import cancellation
from app.rules.errors import err, order_not_found
from app.services.order_service import load_bundle, norm_order_id

TICKET_TYPES = ("warranty", "cancellation")


def check_ticket_allowed(customer_id: str, order_id=None, ticket_type=None) -> dict:
    """Error dict if the ticket is not allowed, else {'order_id': ..., 'ticket_type': ...}."""
    with get_connection() as conn:
        oid = norm_order_id(order_id)
        bundle = load_bundle(conn, customer_id, oid)
        if bundle is None:
            return order_not_found()
        ticket_type = ticket_type.strip().lower() if isinstance(ticket_type, str) else ticket_type
        if ticket_type not in TICKET_TYPES:
            return err("INVALID_TICKET_TYPE", "ticket_type must be 'warranty' or 'cancellation'")
        if ticket_type == "cancellation":
            problem = cancellation.check_cancellation(bundle.order)
        else:
            problem = cancellation.check_warranty_ticket(bundle.items, bundle.delivered, parameter_repo.get_all(conn))
        return problem or {"order_id": oid, "ticket_type": ticket_type}


def create_support_ticket(customer_id: str, order_id=None, ticket_type=None, summary="", *, confirmed=False) -> dict:
    """Writes one row. Refuses unless confirmed=True, which only the 'customer said yes' path passes."""
    if not confirmed:
        return err("CONFIRMATION_REQUIRED", "The customer has not confirmed yet")
    check = check_ticket_allowed(customer_id, order_id, ticket_type)  # re-check just before saving
    if "error_code" in check:
        return check
    ticket_id = str(uuid.uuid4())
    summary = (summary or "").strip() or f"{check['ticket_type']} ticket requested by customer"
    with get_connection() as conn:
        ticket_repo.insert(conn, ticket_id, check["order_id"], customer_id, check["ticket_type"], summary,
                           datetime.now(timezone.utc).isoformat(timespec="seconds"))
    return {"ticket_id": ticket_id, "status": "open", "order_id": check["order_id"],
            "ticket_type": check["ticket_type"]}
