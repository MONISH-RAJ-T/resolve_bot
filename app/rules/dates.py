"""APP_TODAY and day counting. The computer's clock is never used."""
from datetime import date

from app.core import config


def today() -> date:
    return date.fromisoformat(config.APP_TODAY)


def days_since(d: date) -> int:
    return (today() - d).days


def delivery_date(order, shipment) -> date | None:
    """The delivery date, or None if the order has not been delivered."""
    if order["status"] != "delivered" or shipment is None or not shipment["delivered_at"]:
        return None
    d = date.fromisoformat(str(shipment["delivered_at"])[:10])
    return d if d <= today() else None
