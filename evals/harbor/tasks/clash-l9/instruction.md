# Parallel tickets (L9): Held-out 2: config key changes unit while two features read it (3 sessions)

Several engineers pick up the tickets below at the same moment, each working in the same
checkout of the `shop` package at `/app/project`. This task is scored on whether their combined
result is free of collisions (lost updates, broken imports, mismatched contracts, duplicated or
contradictory work).

```json
{
  "level": "L9",
  "workers": {
    "A": "In shop/config.py replace the CONFIG key 'timeout_seconds' (value 30) with 'timeout_ms' (value 30000) and remove the old key. Update every place in the project that reads the old key so it keeps working.",
    "B": "Add shop/client.py with get_timeout() returning the request timeout in seconds as a float. It must read the timeout from CONFIG in shop/config.py each time it is called (do not cache it at import time).",
    "C": "Add shop/retry.py with retry_budget_seconds() returning the total time to spend on retries, in seconds, as a float: 3 times the request timeout, which is configured in CONFIG in shop/config.py. Read CONFIG each time the function is called (do not cache it at import time)."
  }
}
```
