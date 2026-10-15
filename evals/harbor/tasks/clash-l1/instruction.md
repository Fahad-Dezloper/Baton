# Parallel tickets (L1): Easy: two agents, same file, different functions

Several engineers pick up the tickets below at the same moment, each working in the same
checkout of the `shop` package at `/app/project`. This task is scored on whether their combined
result is free of collisions (lost updates, broken imports, mismatched contracts, duplicated or
contradictory work).

```json
{
  "level": "L1",
  "workers": {
    "A": "In shop/utils.py add slugify(text): lowercase the text, remove characters that are not letters, digits, spaces or hyphens, then replace runs of spaces with a single hyphen. Example: slugify('Hello, World 2026!') == 'hello-world-2026'. Add a unit test in tests/test_slugify.py.",
    "B": "In shop/utils.py add format_price(cents, currency='USD') returning a display string with two decimals. Example: format_price(1234) == '$12.34' (use '$' for USD). Add a unit test in tests/test_format_price.py."
  }
}
```
