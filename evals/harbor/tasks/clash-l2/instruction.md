# Parallel tickets (L2): Medium: storage change vs a feature that reads the storage

Several engineers pick up the tickets below at the same moment, each working in the same
checkout of the `shop` package at `/app/project`. This task is scored on whether their combined
result is free of collisions (lost updates, broken imports, mismatched contracts, duplicated or
contradictory work).

```json
{
  "level": "L2",
  "workers": {
    "A": "Make order storage durable: orders created through shop.api must survive a process restart (a new Python process must be able to read orders saved by an earlier one). Implement this in shop/db.py and keep save_order/get_order working. Write any data files inside the project directory.",
    "B": "Add shop/export.py with export_orders_csv(path) that writes all stored orders to a CSV file with header 'id,total_cents,item_count' where item_count is the number of line items in the order. It must work in a fresh Python process after orders were created through shop.api."
  }
}
```
