from collections.abc import Iterable
from uuid import uuid4

from capture.catalog import RecordingCatalog
from handover.format import PackageEnvelope, encode_package
from handover.issued_index import IssuedIndex, IssuedPackage
from handover.project import project_selected_bytes
from handover.selection import resolve_selection
from views.registry import ViewRegistry


def issue_package(
    recordings: RecordingCatalog,
    registry: ViewRegistry,
    index: IssuedIndex,
    recording_id: str,
    names: Iterable[str],
) -> IssuedPackage:
    recording = recordings.get(recording_id)
    selection = resolve_selection(recording_id, registry.get_catalog(recording_id), names)
    previous = index.find_selection(selection)
    if previous is not None:
        return previous
    payload = project_selected_bytes(recording, selection)
    envelope = PackageEnvelope('pkg-' + uuid4().hex, recording_id, payload)
    return index.store(selection, IssuedPackage(envelope.package_id, encode_package(envelope)))
