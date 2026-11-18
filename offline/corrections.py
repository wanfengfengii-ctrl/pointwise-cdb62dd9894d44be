from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from handover.payload import SelectedPayload
from views.integers import encode_unsigned


@dataclass(frozen=True)
class CorrectionRequest:
    view_name: str
    element_index: int
    value: int


class ByteConflict(ValueError):
    """The batch requires two different values at a shared byte reference."""


def resolve_byte_requirements(
    parent: SelectedPayload, requests: Iterable[CorrectionRequest],
) -> dict[int, int]:
    by_name = {view.name: view for view in parent.views}
    required: dict[int, int] = {}
    for request in requests:
        if not isinstance(request, CorrectionRequest):
            raise ValueError('each correction must be a CorrectionRequest')
        if not isinstance(request.view_name, str) or not request.view_name.strip():
            raise ValueError('correction view name must be a nonempty string')
        view = by_name[request.view_name]
        index = request.element_index
        if type(index) is not int or not 0 <= index < len(view.elements):
            raise ValueError(f'element index out of range for {view.name!r}')
        encoded = encode_unsigned(request.value, view.width, view.byteorder)
        for ref, value in zip(view.elements[index], encoded, strict=True):
            if ref in required and required[ref] != value:
                raise ByteConflict(f'conflicting requirements for package byte {ref}')
            required[ref] = value
    if not required:
        raise ValueError('correction batch is empty')
    return required


def apply_byte_requirements(parent: SelectedPayload, requirements: Mapping[int, int]) -> SelectedPayload:
    data = bytearray(parent.data)
    for ref, value in requirements.items():
        data[ref] = value
    return SelectedPayload(bytes(data), parent.views)
