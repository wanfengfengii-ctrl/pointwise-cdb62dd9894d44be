from collections.abc import Iterator
from dataclasses import dataclass

from views.layout import ViewLayout, element_span, element_window_span


@dataclass(frozen=True)
class SourceBytePosition:
    bank_name: str
    offset: int


def iter_element_positions(layout: ViewLayout) -> Iterator[tuple[SourceBytePosition, ...]]:
    """Full containers, in ascending address order, for each logical element."""
    for index in range(layout.count):
        yield tuple(
            SourceBytePosition(layout.bank_name, offset)
            for offset in element_span(layout, index)
        )


def iter_element_window_positions(layout: ViewLayout) -> Iterator[tuple[SourceBytePosition, ...]]:
    """Only the container bytes that carry the selected bits of each element."""
    for index in range(layout.count):
        yield tuple(
            SourceBytePosition(layout.bank_name, offset)
            for offset in element_window_span(layout, index)
        )
