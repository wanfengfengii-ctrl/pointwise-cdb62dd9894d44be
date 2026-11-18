from dataclasses import dataclass

from views.integers import validate_integer_format
from views.windows import normalize_bit_window, window_address_range


@dataclass(frozen=True)
class ViewByteReferences:
    name: str
    width: int
    byteorder: str
    elements: tuple[tuple[int, ...], ...]
    bit_start: int | None = None
    bit_length: int | None = None

    @property
    def span_width(self) -> int:
        """How many container bytes each element reference covers."""
        return len(self.address_range)

    @property
    def address_range(self) -> range:
        return window_address_range(
            self.width, self.byteorder, self.bit_start, self.bit_length,
        )


@dataclass(frozen=True)
class SelectedPayload:
    data: bytes
    views: tuple[ViewByteReferences, ...]


def validate_payload_view(view: ViewByteReferences) -> None:
    if not isinstance(view.name, str) or not view.name.strip():
        raise ValueError('selected view name is empty')
    view.name.encode('utf-8')
    validate_integer_format(view.width, view.byteorder)
    normalize_bit_window(view.width, view.byteorder, view.bit_start, view.bit_length)
    span_width = len(window_address_range(
        view.width, view.byteorder, view.bit_start, view.bit_length,
    ))
    if not isinstance(view.elements, tuple) or not view.elements:
        raise ValueError(f'selected view {view.name!r} has no elements')
    for element in view.elements:
        if not isinstance(element, tuple) or len(element) != span_width:
            raise ValueError('element reference count differs from its container span')
        if len(set(element)) != span_width:
            raise ValueError('an element must address distinct consecutive source bytes')


def validate_payload_references(payload: SelectedPayload) -> None:
    if not isinstance(payload.data, bytes) or not payload.data:
        raise ValueError('selected payload must contain bytes')
    if not isinstance(payload.views, tuple) or not payload.views:
        raise ValueError('selected payload must contain views')
    names = set()
    covered = set()
    for view in payload.views:
        if not isinstance(view, ViewByteReferences):
            raise ValueError('invalid selected view')
        validate_payload_view(view)
        if view.name in names:
            raise ValueError('selected view name is empty or repeated')
        names.add(view.name)
        for element in view.elements:
            for ref in element:
                if type(ref) is not int or not 0 <= ref < len(payload.data):
                    raise ValueError('byte reference outside selected payload')
            covered.update(element)
    if len(covered) != len(payload.data):
        raise ValueError('selected payload contains unreferenced bytes')
