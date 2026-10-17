# Parallel tickets (L8): Held-out 2: function rename vs new callers of the old name (3 sessions)

Several engineers pick up the tickets below at the same moment, each working in the same
checkout of the `shop` package at `/app/project`. This task is scored on whether their combined
result is free of collisions (lost updates, broken imports, mismatched contracts, duplicated or
contradictory work).

```json
{
  "level": "L8",
  "workers": {
    "A": "In shop/db.py rename the function get_order to load_order (same behaviour). Update every caller in the project, including shop/api.py and the files under tests/, so that nothing refers to get_order any more.",
    "B": "Add shop/audit.py with order_total(order_id): it returns the total_cents of the stored order, or None when no such order exists. Read the order with shop.db.get_order(order_id).",
    "C": "Add shop.api.order_exists(order_id) in shop/api.py: it returns True if an order with that id is stored, otherwise False. Read the order with db.get_order(order_id)."
  }
}
```
