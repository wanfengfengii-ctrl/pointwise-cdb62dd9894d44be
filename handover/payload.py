from dataclasses import dataclass

from views.integers import validate_integer_format


@dataclass(frozen=True)
class ViewByteReferences:
    name: str
    width: int
    byteorder: str
    elements: tuple[tuple[int, ...], ...]


@dataclass(frozen=True)
class SelectedPayload:
    data: bytes
    views: tuple[ViewByteReferences, ...]


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
        if not isinstance(view.name, str) or not view.name.strip() or view.name in names:
            raise ValueError('selected view name is empty or repeated')
        view.name.encode('utf-8')
        names.add(view.name)
        validate_integer_format(view.width, view.byteorder)
        if not isinstance(view.elements, tuple) or not view.elements:
            raise ValueError(f'selected view {view.name!r} has no elements')
        for element in view.elements:
            if not isinstance(element, tuple) or len(element) != view.width:
                raise ValueError('element reference count differs from width')
            for ref in element:
                if type(ref) is not int or not 0 <= ref < len(payload.data):
                    raise ValueError('byte reference outside selected payload')
            if len(set(element)) != view.width:
                raise ValueError('an element must address distinct consecutive source bytes')
            covered.update(element)
    if len(covered) != len(payload.data):
        raise ValueError('selected payload contains unreferenced bytes')
