"""Order queries. Every order lookup also filters by customer_id, so another customer's order is never returned."""


def find_order(conn, customer_id: str, order_id: str):
    return conn.execute(
        "SELECT * FROM orders WHERE order_id = ? AND customer_id = ?", (order_id, customer_id)
    ).fetchone()


def list_orders(conn, customer_id: str, status: str | None = None, limit: int = 30):
    sql, args = "SELECT * FROM orders WHERE customer_id = ?", [customer_id]
    if status:
        sql += " AND status = ?"
        args.append(status)
    sql += " ORDER BY order_date DESC LIMIT ?"
    args.append(limit)
    return conn.execute(sql, args).fetchall()


def get_items(conn, order_id: str):
    return conn.execute(
        """SELECT oi.*, p.name, p.category, p.returnable, p.warranty_class
           FROM order_items oi JOIN products p ON p.product_id = oi.product_id
           WHERE oi.order_id = ? ORDER BY oi.item_id""",
        (order_id,),
    ).fetchall()


def get_shipment(conn, order_id: str):
    return conn.execute("SELECT * FROM shipments WHERE order_id = ?", (order_id,)).fetchone()
