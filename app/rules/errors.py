"""Error dicts shared by rules, services and tools."""

NOT_FOUND_TEXT = "I couldn't find that order on your account."


def err(code: str, message: str, **extra) -> dict:
    return {"error_code": code, "message": message, **extra}


def order_not_found() -> dict:
    """Same error whether the order does not exist or belongs to someone else."""
    return err("ORDER_NOT_FOUND", NOT_FOUND_TEXT)
