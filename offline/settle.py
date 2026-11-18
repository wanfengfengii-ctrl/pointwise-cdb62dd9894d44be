from collections.abc import Callable, Iterable

from offline.corrections import CorrectionRequest, apply_byte_requirements, resolve_byte_requirements
from offline.lineage import build_receipt, new_child_record
from offline.revisions import RevisionStore, StoredReceipt


def correct_package(
    store: RevisionStore,
    parent_id: str,
    requests: Iterable[CorrectionRequest],
    *,
    before_commit: Callable[[], None] | None = None,
) -> tuple[str, StoredReceipt]:
    parent = store.get(parent_id)
    try:
        batch = tuple(requests)
    except TypeError as error:
        raise ValueError('correction batch must be iterable') from error
    requirements = resolve_byte_requirements(parent.package.payload, batch)
    payload = apply_byte_requirements(parent.package.payload, requirements)
    child = new_child_record(parent, payload)
    receipt = build_receipt(child, len(batch))
    store.commit_correction(child, receipt, before_commit=before_commit)
    return child.package_id, receipt
