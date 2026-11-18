from capture.banks import read_bank
from capture.catalog import StoredRecording
from handover.payload import SelectedPayload, ViewByteReferences
from handover.selection import ResolvedSelection
from views.coordinates import SourceBytePosition, iter_element_positions


def project_selected_bytes(
    recording: StoredRecording, selection: ResolvedSelection,
) -> SelectedPayload:
    if recording.recording_id != selection.recording_id:
        raise ValueError('selection belongs to a different recording')
    positions: dict[SourceBytePosition, int] = {}
    data = bytearray()
    views = []
    for layout in selection.views:
        bank = read_bank(recording.banks, layout.bank_name)
        elements = []
        for original_positions in iter_element_positions(layout):
            refs = []
            for position in original_positions:
                if position not in positions:
                    positions[position] = len(data)
                    data.append(bank[position.offset])
                refs.append(positions[position])
            elements.append(tuple(refs))
        views.append(ViewByteReferences(layout.name, layout.width, layout.byteorder, tuple(elements)))
    return SelectedPayload(bytes(data), tuple(views))
