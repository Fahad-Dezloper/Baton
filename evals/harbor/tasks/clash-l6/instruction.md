# Parallel tickets (L6): Held-out: stock reservation across modules (3 sessions)

Several engineers pick up the tickets below at the same moment, each working in the same
checkout of the `shop` package at `/app/project`. This task is scored on whether their combined
result is free of collisions (lost updates, broken imports, mismatched contracts, duplicated or
contradictory work).

```json
{
  "level": "L6",
  "workers": {
    "A": "Add shop/inventory.py. It keeps stock per sku; every sku starts with 10 units. Expose available(sku) -> int, reserve(sku, qty) which raises ValueError if qty is more than is available, and release(sku, qty) which returns units to stock.",
    "B": "Make shop.api.create_order refuse to create an order when any line item asks for more units than are available (raise ValueError and create nothing). When an order is created, reserve its items from stock. Use the stock module shop/inventory.py.",
    "C": "Add shop.api.cancel_order(order_id): it removes the order, returns its reserved units to stock and returns True; it returns False if the order does not exist. Use the stock module shop/inventory.py."
  }
}
```
