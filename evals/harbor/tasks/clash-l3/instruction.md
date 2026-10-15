# Parallel tickets (L3): Hard: three agents, shared model, unspecified internals

Several engineers pick up the tickets below at the same moment, each working in the same
checkout of the `shop` package at `/app/project`. This task is scored on whether their combined
result is free of collisions (lost updates, broken imports, mismatched contracts, duplicated or
contradictory work).

```json
{
  "level": "L3",
  "workers": {
    "A": "Add discount support. shop.api.create_order(order_id, items, discount_percent=0) must accept a percentage from 0 to 100. The order's total_cents (as returned by shop.api responses) must reflect the discount, i.e. be the subtotal after discount.",
    "B": "Add tax. Add 'tax_rate' to CONFIG in shop/config.py with default 0.08. shop.api.fetch_order(order_id) must also return 'tax_cents' = round(tax_rate * the order's total_cents as the order computes it).",
    "C": "Add shop/report.py with order_summary(order_id) returning a dict with exactly these keys: id, subtotal_cents (before discount), discount_cents, tax_cents, total_cents (after discount plus tax). Use whatever the order and api already expose for discount and tax."
  }
}
```
