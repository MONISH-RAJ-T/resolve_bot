def get_all(conn) -> dict:
    """policy_parameters as {key: value}. Every business number comes from here."""
    return {r["key"]: r["value"] for r in conn.execute("SELECT key, value FROM policy_parameters")}
