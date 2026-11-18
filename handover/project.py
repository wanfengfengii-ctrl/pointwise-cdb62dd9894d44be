from capture.banks import read_bank
from capture.catalog import StoredRecording
from handover.payload import SelectedPayload, ViewByteReferences
from handover.selection import ResolvedSelection
from views.coordinates import SourceBytePosition, iter_element_window_positions


def project_selected_bytes(
    recording: StoredRecording, selection: ResolvedSelection,
) -> SelectedPayload:
    """Copy only the source bytes the selection actually touches.

    For a whole-word view every container byte is touched; for a bit window
    only the container bytes that carry the window bits are copied, each one
    with its complete original value.  A shared (bank, offset) position is
    stored once, so equal values at different positions stay independent.
    """
    if recording.recording_id != selection.recording_id:
        raise ValueError('selection belongs to a different recording')
    positions: dict[SourceBytePosition, int] = {}
    data = bytearray()
    views = []
    for layout in selection.views:
        bank = read_bank(recording.banks, layout.bank_name)
        elements = []
        for original_positions in iter_element_window_positions(layout):
            refs = []
            for position in original_positions:
                if position not in positions:
                    positions[position] = len(data)
                    data.append(bank[position.offset])
                refs.append(positions[position])
            elements.append(tuple(refs))
        views.append(ViewByteReferences(
            layout.name, layout.width, layout.byteorder, tuple(elements),
            layout.bit_start, layout.bit_length,
        ))
    return SelectedPayload(bytes(data), tuple(views))
