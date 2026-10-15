# Parallel tickets (L4): Very hard: refactor running while features land

Several engineers pick up the tickets below at the same moment, each working in the same
checkout of the `shop` package at `/app/project`. This task is scored on whether their combined
result is free of collisions (lost updates, broken imports, mismatched contracts, duplicated or
contradictory work).

```json
{
  "level": "L4",
  "workers": {
    "A": "Rename shop/db.py to shop/store.py (keep the function names) and update every import in the project, including tests.",
    "B": "Add shop.api.cancel_order(order_id): returns True and marks the order cancelled; fetch_order responses gain a 'status' key that is 'open' by default and 'cancelled' after cancel_order. Use the project's order storage module.",
    "C": "Write tests/test_api_more.py with tests for create_order and fetch_order, including resetting stored state between tests by using the storage module directly.",
    "D": "Change CONFIG in shop/config.py to a nested format: CONFIG = {'currency': 'USD', 'limits': {'timeout_seconds': 30}}. Update any code that reads timeout_seconds.",
    "E": "Add shop/log.py exposing get_logger(name). Add 'log_level': 'INFO' to CONFIG in shop/config.py and make the functions in shop/api.py log each call using that logger."
  }
}
```
