from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class ViewTotals:
    count: int
    total: int
    minimum: int
    maximum: int


def summarize_values(values: Sequence[int]) -> ViewTotals:
    if not values:
        raise ValueError('view totals require at least one integer')
    return ViewTotals(len(values), sum(values), min(values), max(values))


def sum_delta(parent: ViewTotals, child: ViewTotals) -> int:
    return child.total - parent.total
