"""Warranty length and end date. Months come from policy_parameters, never from this file."""
from datetime import date

from dateutil.relativedelta import relativedelta

from app.rules import dates


def warranty_months(warranty_class: str, params: dict) -> int | None:
    if warranty_class == "standard":
        return int(params["standard_warranty_months"])
    if warranty_class == "extended":
        return int(params["extended_warranty_months"])
    return None  # "none" = no warranty


def warranty_info(item, delivered: date | None, params: dict) -> dict:
    months = warranty_months(item["warranty_class"], params)
    if months is None or delivered is None:
        return {"warranty_months": months, "warranty_end_date": None, "warranty_active": False}
    end = delivered + relativedelta(months=months)  # month-end safe: 31 Jan + 1 month = 28/29 Feb
    return {
        "warranty_months": months,
        "warranty_end_date": end.isoformat(),
        "warranty_active": dates.today() <= end,  # the last day is still covered
    }
