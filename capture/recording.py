from collections.abc import Iterable, Mapping

from capture.banks import normalize_banks
from capture.catalog import RecordingCatalog
from capture.integrity import fingerprint_banks, same_named_banks


def register_recording(
    catalog: RecordingCatalog,
    external_name: str,
    banks: Mapping[str, bytes] | Iterable[tuple[str, bytes]],
) -> str:
    if not isinstance(external_name, str) or not external_name.strip():
        raise ValueError('external recording name must be a nonempty string')
    external_name.encode('utf-8')
    normalized = normalize_banks(banks)
    fingerprint = fingerprint_banks(normalized)
    record = catalog.find_by_name(external_name)
    if record is None:
        record = catalog.store(external_name, normalized, fingerprint)
    if record.fingerprint != fingerprint or not same_named_banks(record.banks, normalized):
        raise ValueError(f'recording name already binds different banks: {external_name!r}')
    return record.recording_id
