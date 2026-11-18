from capture.banks import read_bank
from capture.catalog import StoredRecording
from handover.payload import SelectedPayload, ViewByteReferences
from views.coordinates import iter_element_positions
from views.integers import decode_unsigned
from views.layout import ViewLayout


def read_source_values(recording: StoredRecording, view: ViewLayout) -> tuple[int, ...]:
    bank = read_bank(recording.banks, view.bank_name)
    return tuple(
        decode_unsigned(bytes(bank[position.offset] for position in element), view.width, view.byteorder)
        for element in iter_element_positions(view)
    )


def read_package_values(payload: SelectedPayload, view: ViewByteReferences) -> tuple[int, ...]:
    return tuple(
        decode_unsigned(bytes(payload.data[ref] for ref in element), view.width, view.byteorder)
        for element in view.elements
    )
