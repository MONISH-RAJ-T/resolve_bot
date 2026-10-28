"""Returns: tool 3 (check_return_eligibility) and tool 4 (create_return_request)."""
import json
import uuid
from datetime import datetime, timezone

from app.core.database import get_connection
from app.repositories import parameter_repo, return_repo
from app.rules import returns as return_rules
from app.rules.errors import err, order_not_found
from app.services.order_service import load_bundle, norm_item_ids, norm_order_id


def _norm_reason(raw):
    return raw.strip().lower().replace(" ", "_") if isinstance(raw, str) else raw


def check_return_eligibility(customer_id: str, order_id=None, item_ids=None, reason=None) -> dict:
    with get_connection() as conn:
        oid = norm_order_id(order_id)
        bundle = load_bundle(conn, customer_id, oid)
        if bundle is None:
            return order_not_found()
        result = return_rules.check_return(bundle.items, norm_item_ids(item_ids), _norm_reason(reason),
                                           bundle.delivered, parameter_repo.get_all(conn))
        if "error_code" not in result:
            result["order_id"] = oid
        return result


def create_return_request(customer_id: str, order_id=None, item_ids=None, reason=None, *, confirmed=False) -> dict:
    """Writes one row. Refuses unless confirmed=True, which only the 'customer said yes' path passes."""
    if not confirmed:
        return err("CONFIRMATION_REQUIRED", "The customer has not confirmed yet")
    check = check_return_eligibility(customer_id, order_id, item_ids, reason)  # re-check just before saving
    if "error_code" in check:
        return check
    request_id = str(uuid.uuid4())
    with get_connection() as conn:
        return_repo.insert(conn, request_id, check["order_id"], customer_id, json.dumps(check["item_ids"]),
                           check["reason"], datetime.now(timezone.utc).isoformat(timespec="seconds"))
    return {"request_id": request_id, "status": "requested", "order_id": check["order_id"],
            "item_ids": check["item_ids"], "item_names": check["item_names"], "reason": check["reason"]}
