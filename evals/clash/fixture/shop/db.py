_ORDERS = {}


def save_order(order):
    _ORDERS[order.id] = order


def get_order(order_id):
    return _ORDERS.get(order_id)
