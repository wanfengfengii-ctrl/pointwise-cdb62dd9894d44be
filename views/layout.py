from dataclasses import dataclass

from views.windows import window_address_range


@dataclass(frozen=True)
class ViewLayout:
    name: str
    bank_name: str
    start: int
    stride: int
    count: int
    width: int
    byteorder: str
    bit_start: int | None = None
    bit_length: int | None = None


def element_span(layout: ViewLayout, index: int) -> range:
    """Container addresses, in ascending order, that the element occupies."""
    if type(index) is not int or not 0 <= index < layout.count:
        raise ValueError(f'element index out of range for {layout.name!r}')
    start = layout.start + index * layout.stride
    return range(start, start + layout.width)


def element_window_span(layout: ViewLayout, index: int) -> range:
    """Container addresses that actually carry the element's selected bits.

    For a whole-word view this equals ``element_span``.  For a bit window only
    the container bytes touched by the window are present in a handover.
    """
    span = element_span(layout, index)
    addresses = window_address_range(
        layout.width, layout.byteorder, layout.bit_start, layout.bit_length,
    )
    return range(span.start + addresses.start, span.start + addresses.stop)


def covered_bounds(layout: ViewLayout) -> tuple[int, int]:
    """Return the lowest byte and the exclusive upper bound of a valid geometry."""
    last_start = layout.start + (layout.count - 1) * layout.stride
    return min(layout.start, last_start), max(layout.start, last_start) + layout.width
