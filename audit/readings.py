from capture.banks import read_bank
from capture.catalog import StoredRecording
from handover.payload import SelectedPayload, ViewByteReferences
from views.coordinates import iter_element_positions, iter_element_window_positions
from views.integers import decode_unsigned
from views.layout import ViewLayout
from views.windows import decode_address_bytes, window_address_range


def _window_addresses(width, byteorder, bit_start, bit_length) -> tuple[int, ...]:
    return tuple(window_address_range(width, byteorder, bit_start, bit_length))


def read_source_values(recording: StoredRecording, view: ViewLayout) -> tuple[int, ...]:
    bank = read_bank(recording.banks, view.bank_name)
    if view.bit_start is None and view.bit_length is None:
        return tuple(
            decode_unsigned(bytes(bank[position.offset] for position in element), view.width, view.byteorder)
            for element in iter_element_positions(view)
        )
    addresses = _window_addresses(view.width, view.byteorder, view.bit_start, view.bit_length)
    return tuple(
        decode_address_bytes(
            {address: bank[position.offset] for address, position in zip(addresses, element, strict=True)},
            view.width, view.byteorder, view.bit_start, view.bit_length,
        )
        for element in iter_element_window_positions(view)
    )


def read_package_values(payload: SelectedPayload, view: ViewByteReferences) -> tuple[int, ...]:
    if view.bit_start is None and view.bit_length is None:
        return tuple(
            decode_unsigned(bytes(payload.data[ref] for ref in element), view.width, view.byteorder)
            for element in view.elements
        )
    addresses = _window_addresses(view.width, view.byteorder, view.bit_start, view.bit_length)
    return tuple(
        decode_address_bytes(
            {address: payload.data[ref] for address, ref in zip(addresses, element, strict=True)},
            view.width, view.byteorder, view.bit_start, view.bit_length,
        )
        for element in view.elements
    )
