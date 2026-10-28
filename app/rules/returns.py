"""Return rules, checked in order; stops at the first failure.
(Order ownership is checked by the caller before this runs.)"""
from app.rules import dates
from app.rules.errors import err

REASONS = ("changed_mind", "defective")


def check_return(items, requested_ids, reason, delivered, params) -> dict:
    if reason not in REASONS:
        return err("INVALID_REASON", "reason must be 'changed_mind' or 'defective'")
    if not requested_ids:
        return err("INVALID_ITEM", "No items were given")
    by_id = {i["item_id"]: i for i in items}
    for iid in requested_ids:
        if iid not in by_id:
            return err("INVALID_ITEM", f"Item {iid} is not in this order", item_id=iid)
    if delivered is None:
        return err("NOT_DELIVERED", "This order has not been delivered yet")

    chosen = [by_id[i] for i in dict.fromkeys(requested_ids)]

    # 2. the product must be returnable at all
    for it in chosen:
        if it["returnable"] == "no":
            return err("NON_RETURNABLE", f"{it['name']} cannot be returned", item_id=it["item_id"])

    # 3. within the return window ("30 days" means 30 or fewer)
    window = int(params["return_window_days"])
    days = dates.days_since(delivered)
    if days > window:
        return err("RETURN_WINDOW_EXPIRED",
                   f"Delivered {days} days ago; the return window is {window} days",
                   days_since_delivery=days, return_window_days=window)

    # 4. opened + changed_mind + a product that is only returnable unopened
    if reason == "changed_mind":
        for it in chosen:
            if it["opened"] and it["returnable"] == "unopened_only":
                return err("OPENED_NOT_RETURNABLE",
                           f"{it['name']} is opened and can only be returned unopened for a change of mind",
                           item_id=it["item_id"])

    return {"result": "eligible", "item_ids": [i["item_id"] for i in chosen],
            "item_names": [i["name"] for i in chosen], "reason": reason,
            "days_since_delivery": days, "return_window_days": window}
