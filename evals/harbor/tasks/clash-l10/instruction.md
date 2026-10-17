# Parallel tickets (L10): Held-out 2: three sessions register entries in one shared registry file (3 sessions)

Several engineers pick up the tickets below at the same moment, each working in the same
checkout of the `shop` package at `/app/project`. This task is scored on whether their combined
result is free of collisions (lost updates, broken imports, mismatched contracts, duplicated or
contradictory work).

```json
{
  "level": "L10",
  "workers": {
    "A": "shop/validators.py holds a module-level dict VALIDATORS mapping a name to a function(value) -> bool, and a function validate(kind, value) that returns VALIDATORS[kind](value) (an unknown kind raises KeyError). Add the validator 'sku' there: True only for a non-empty str made of lowercase letters and digits. Create the file if it does not exist yet.",
    "B": "shop/validators.py holds a module-level dict VALIDATORS mapping a name to a function(value) -> bool, and a function validate(kind, value) that returns VALIDATORS[kind](value) (an unknown kind raises KeyError). Add the validator 'qty' there: True only for an int from 1 to 999 inclusive. Create the file if it does not exist yet.",
    "C": "shop/validators.py holds a module-level dict VALIDATORS mapping a name to a function(value) -> bool, and a function validate(kind, value) that returns VALIDATORS[kind](value) (an unknown kind raises KeyError). Add the validator 'email' there: True only for a str that contains exactly one '@' and has a '.' somewhere after the '@'. Create the file if it does not exist yet."
  }
}
```
