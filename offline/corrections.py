from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from handover.payload import SelectedPayload
from views.integers import encode_unsigned
from views.windows import bit_address, normalize_bit_window, window_value_limit


@dataclass(frozen=True)
class CorrectionRequest:
    view_name: str
    element_index: int
    value: int


class ByteConflict(ValueError):
    """The batch requires two different values at a shared physical bit or byte."""


def _declared_bits(view, value) -> dict[tuple[int, int], int]:
    """Return {(address, bit): value} for every bit the target range declares.

    ``address`` is the container address index (0..width-1) and ``bit`` is the
    bit index inside that physical byte, so keys identify physical bits.
    """
    if view.bit_start is None and view.bit_length is None:
        raw = encode_unsigned(value, view.width, view.byteorder)
        return {
            (address, bit): (raw[address] >> bit) & 1
            for address in range(view.width)
            for bit in range(8)
        }
    start, length = normalize_bit_window(
        view.width, view.byteorder, view.bit_start, view.bit_length,
    )
    if type(value) is not int or not 0 <= value <= window_value_limit(length):
        raise ValueError(f'unsigned bit window is outside the {length}-bit range')
    bits = {}
    for offset in range(length):
        absolute = start + offset
        address = bit_address(view.width, view.byteorder, absolute)
        bits[(address, absolute % 8)] = (value >> offset) & 1
    return bits


def resolve_bit_requirements(
    parent: SelectedPayload, requests: Iterable[CorrectionRequest],
) -> dict[tuple[int, int], int]:
    """Map each declared physical package bit to its required value."""
    by_name = {view.name: view for view in parent.views}
    required: dict[tuple[int, int], int] = {}
    for request in requests:
        if not isinstance(request, CorrectionRequest):
            raise ValueError('each correction must be a CorrectionRequest')
        if not isinstance(request.view_name, str) or not request.view_name.strip():
            raise ValueError('correction view name must be a nonempty string')
        view = by_name[request.view_name]
        index = request.element_index
        if type(index) is not int or not 0 <= index < len(view.elements):
            raise ValueError(f'element index out of range for {view.name!r}')
        element = view.elements[index]
        span = view.address_range
        for (address, bit), bit_value in _declared_bits(view, request.value).items():
            ref = element[address - span.start]
            key = (ref, bit)
            if key in required and required[key] != bit_value:
                raise ByteConflict(f'conflicting requirements for package byte {ref} bit {bit}')
            required[key] = bit_value
    if not required:
        raise ValueError('correction batch is empty')
    return required


def resolve_byte_requirements(
    parent: SelectedPayload, requests: Iterable[CorrectionRequest],
) -> dict[int, int]:
    """Compute the new value of every package byte touched by the batch.

    Bits that no request declares keep the parent value.
    """
    bits = resolve_bit_requirements(parent, requests)
    data = bytearray(parent.data)
    touched: dict[int, int] = {}
    declared: dict[int, list[tuple[int, int]]] = {}
    for (ref, bit), bit_value in bits.items():
        declared.setdefault(ref, []).append((bit, bit_value))
    for ref, assignments in declared.items():
        value = data[ref]
        for bit, bit_value in assignments:
            value = (value & ~(1 << bit)) | (bit_value << bit)
        touched[ref] = value
    return touched


def apply_byte_requirements(parent: SelectedPayload, requirements: Mapping[int, int]) -> SelectedPayload:
    data = bytearray(parent.data)
    for ref, value in requirements.items():
        data[ref] = value
    return SelectedPayload(bytes(data), parent.views)
