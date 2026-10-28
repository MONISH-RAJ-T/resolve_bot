"""Rules for the two ticket types. Each returns None if allowed, or an error dict."""
from app.rules.errors import err
from app.rules.warranty import warranty_info


def check_cancellation(order) -> dict | None:
    """Only 'processing' orders can be cancelled."""
    if order["status"] == "processing":
        return None
    if order["status"] == "cancelled":
        return err("ORDER_ALREADY_CANCELLED", "This order is already cancelled")
    return err("ORDER_ALREADY_SHIPPED", "This order has already shipped and cannot be cancelled")


def check_warranty_ticket(items, delivered, params) -> dict | None:
    """Needs a delivered order and at least one item still under warranty."""
    if delivered is None:
        return err("NOT_DELIVERED", "This order has not been delivered yet")
    infos = [warranty_info(i, delivered, params) for i in items]
    if any(w["warranty_active"] for w in infos):
        return None
    if all(w["warranty_months"] is None for w in infos):
        return err("NO_WARRANTY", "None of the items in this order have a warranty")
    return err("WARRANTY_EXPIRED", "The warranty has ended for all items in this order")
