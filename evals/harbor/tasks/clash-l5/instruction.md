# Parallel tickets (L5): Extreme: duplicate tickets, signature change, contradictory requirements

Several engineers pick up the tickets below at the same moment, each working in the same
checkout of the `shop` package at `/app/project`. This task is scored on whether their combined
result is free of collisions (lost updates, broken imports, mismatched contracts, duplicated or
contradictory work).

```json
{
  "level": "L5",
  "workers": {
    "A": "Add rate limiting to shop.api.create_order: at most 5 calls per client_id per rolling minute; extra calls must be rejected (raise an exception or return a dict with an 'error' key). Clients are independent.",
    "B": "Add rate limiting to shop.api.create_order: at most 5 calls per client_id per rolling minute; extra calls must be rejected (raise an exception or return a dict with an 'error' key). Clients are independent.",
    "C": "Add rate limiting to shop.api.create_order: at most 5 calls per client_id per rolling minute; extra calls must be rejected (raise an exception or return a dict with an 'error' key). Clients are independent.",
    "D": "Add a required keyword parameter client_id to shop.api.create_order and shop.api.fetch_order (for audit). Keep order_id and items parameter names unchanged and update existing callers and tests.",
    "E": "Security requirement for rate limiting on shop.api.create_order (5 calls per client_id per rolling minute, extras rejected): the limiter state must persist across process restarts.",
    "F": "Performance requirement for rate limiting on shop.api.create_order (5 calls per client_id per rolling minute, extras rejected): no file or disk I/O on the request path."
  }
}
```
