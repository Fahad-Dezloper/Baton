# Parallel tickets (L7): Held-out: four additions to one file (4 sessions)

Several engineers pick up the tickets below at the same moment, each working in the same
checkout of the `shop` package at `/app/project`. This task is scored on whether their combined
result is free of collisions (lost updates, broken imports, mismatched contracts, duplicated or
contradictory work).

```json
{
  "level": "L7",
  "workers": {
    "A": "Add shop.api.list_order_ids() returning a sorted list of all stored order ids. Add whatever storage helper you need.",
    "B": "Add shop.api.delete_order(order_id): it removes the order and returns True, or returns False if the order does not exist.",
    "C": "Make shop.api.create_order raise ValueError, and create nothing, when items is empty or any item has qty <= 0.",
    "D": "Add shop.api.order_count() returning the number of stored orders."
  }
}
```
