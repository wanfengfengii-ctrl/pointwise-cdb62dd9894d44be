from dataclasses import dataclass


@dataclass(frozen=True)
class ViewLayout:
    name: str
    bank_name: str
    start: int
    stride: int
    count: int
    width: int
    byteorder: str


def element_span(layout: ViewLayout, index: int) -> range:
    if type(index) is not int or not 0 <= index < layout.count:
        raise ValueError(f'element index out of range for {layout.name!r}')
    start = layout.start + index * layout.stride
    return range(start, start + layout.width)


def covered_bounds(layout: ViewLayout) -> tuple[int, int]:
    """Return the lowest byte and the exclusive upper bound of a valid geometry."""
    last_start = layout.start + (layout.count - 1) * layout.stride
    return min(layout.start, last_start), max(layout.start, last_start) + layout.width
