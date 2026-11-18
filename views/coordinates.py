from collections.abc import Iterator
from dataclasses import dataclass

from views.layout import ViewLayout, element_span


@dataclass(frozen=True)
class SourceBytePosition:
    bank_name: str
    offset: int


def iter_element_positions(layout: ViewLayout) -> Iterator[tuple[SourceBytePosition, ...]]:
    for index in range(layout.count):
        yield tuple(
            SourceBytePosition(layout.bank_name, offset)
            for offset in element_span(layout, index)
        )
