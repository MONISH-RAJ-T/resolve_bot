"""Order lookups (tool 1: get_orders) plus the values our code works out:
delivery date, days since delivery, warranty end date and whether the warranty is active."""
import re
from dataclasses import dataclass
from datetime import date

from app.core.database import get_connection
from app.repositories import order_repo, parameter_repo
from app.rules import dates
from app.rules.errors import err, order_not_found
from app.rules.warranty import warranty_info

STATUSES = ("processing", "shipped", "delivered", "cancelled")


@dataclass
class OrderBundle:
    order: object
    items: list
    shipment: object
    delivered: date | None


def norm_order_id(raw):
    """'ss10458', 'SS 10458' and 'SS-10458' all become 'SS-10458'."""
    if not isinstance(raw, str):
        return None
    s = raw.strip().upper().replace(" ", "")
    m = re.fullmatch(r"SS-?(\d+)", s)
    return f"SS-{m.group(1)}" if m else s


def norm_item_ids(raw) -> list[str]:
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, list):
        return []
    return [str(x).strip().upper() for x in raw if str(x).strip()]


def load_bundle(conn, customer_id: str, order_id) -> OrderBundle | None:
    """The order with its items and shipment - only if it belongs to this customer."""
    order = order_repo.find_order(conn, customer_id, order_id) if order_id else None
    if order is None:
        return None
    shipment = order_repo.get_shipment(conn, order["order_id"])
    return OrderBundle(order, order_repo.get_items(conn, order["order_id"]), shipment,
                       dates.delivery_date(order, shipment))


def build_view(b: OrderBundle, params: dict) -> dict:
    view = {
        "order_id": b.order["order_id"], "status": b.order["status"], "order_date": str(b.order["order_date"])[:10],
        "total": b.order["total"], "shipping_fee": b.order["shipping_fee"],
        "delivery_date": b.delivered.isoformat() if b.delivered else None,
        "days_since_delivery": dates.days_since(b.delivered) if b.delivered else None,
        "shipment": None, "items": [],
    }
    if b.shipment:
        view["shipment"] = {k: b.shipment[k] for k in
                            ("carrier", "tracking_no", "status", "shipped_at", "delivered_at", "eta", "original_eta")}
        threshold = params.get("delay_ticket_threshold_days")
        if b.shipment["original_eta"] and not b.delivered and b.order["status"] == "shipped" and threshold is not None:
            late = (dates.today() - date.fromisoformat(b.shipment["original_eta"])).days
            if late > 0:
                view["days_past_original_eta"] = late
                view["more_than_threshold_days_late"] = late > int(threshold)
    for it in b.items:
        view["items"].append({
            "item_id": it["item_id"], "name": it["name"], "category": it["category"], "qty": it["qty"],
            "unit_price": it["unit_price"], "opened": bool(it["opened"]),
            **warranty_info(it, b.delivered, params)})
    return view


def get_orders(customer_id: str, order_id=None, status=None) -> dict:
    with get_connection() as conn:
        params = parameter_repo.get_all(conn)
        if order_id:
            bundle = load_bundle(conn, customer_id, norm_order_id(order_id))
            if bundle is None:
                return order_not_found()
            return {"orders": [build_view(bundle, params)]}
        if status and status not in STATUSES:
            return err("INVALID_STATUS", f"status must be one of {', '.join(STATUSES)}")
        views = []
        for o in order_repo.list_orders(conn, customer_id, status):
            views.append(build_view(load_bundle(conn, customer_id, o["order_id"]), params))
        return {"orders": views}
