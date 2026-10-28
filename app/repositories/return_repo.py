def insert(conn, request_id, order_id, customer_id, item_ids_json, reason, created_at) -> None:
    conn.execute(
        "INSERT INTO return_requests (request_id, order_id, customer_id, item_ids, reason, status, created_at) "
        "VALUES (?, ?, ?, ?, ?, 'requested', ?)",
        (request_id, order_id, customer_id, item_ids_json, reason, created_at))
    conn.commit()
