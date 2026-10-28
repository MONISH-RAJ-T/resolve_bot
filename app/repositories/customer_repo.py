def exists(conn, customer_id: str) -> bool:
    return conn.execute("SELECT 1 FROM customers WHERE customer_id = ?", (customer_id,)).fetchone() is not None
