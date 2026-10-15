from shop.models import Order, Item
from shop import db


def create_order(order_id, items):
    order = Order(id=order_id, items=[Item(**i) for i in items])
    db.save_order(order)
    return {"id": order.id, "total_cents": order.total_cents}


def fetch_order(order_id):
    order = db.get_order(order_id)
    if order is None:
        return None
    return {"id": order.id, "total_cents": order.total_cents}
