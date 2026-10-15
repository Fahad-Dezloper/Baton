from dataclasses import dataclass, field
from typing import List


@dataclass
class Item:
    sku: str
    price_cents: int
    qty: int = 1


@dataclass
class Order:
    id: str
    items: List[Item] = field(default_factory=list)

    @property
    def total_cents(self) -> int:
        return sum(i.price_cents * i.qty for i in self.items)
