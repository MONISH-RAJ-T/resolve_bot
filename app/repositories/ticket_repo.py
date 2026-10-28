def insert(conn, ticket_id, order_id, customer_id, ticket_type, summary, created_at) -> None:
    conn.execute(
        "INSERT INTO support_tickets (ticket_id, order_id, customer_id, ticket_type, summary, status, created_at) "
        "VALUES (?, ?, ?, ?, ?, 'open', ?)",
        (ticket_id, order_id, customer_id, ticket_type, summary, created_at))
    conn.commit()
