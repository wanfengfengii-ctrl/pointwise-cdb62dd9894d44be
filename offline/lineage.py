from uuid import uuid4

from handover.format import PackageEnvelope
from handover.payload import SelectedPayload
from offline.revisions import RevisionSnapshot, StoredReceipt


def new_child_record(parent: RevisionSnapshot, payload: SelectedPayload) -> RevisionSnapshot:
    package = PackageEnvelope('rev-' + uuid4().hex, parent.package.recording_id, payload)
    return RevisionSnapshot(package, parent.package_id)


def build_receipt(child: RevisionSnapshot, request_count: int) -> StoredReceipt:
    if child.parent_id is None:
        raise ValueError('a correction receipt requires a direct parent')
    if type(request_count) is not int or request_count < 1:
        raise ValueError('a correction receipt requires at least one request')
    return StoredReceipt(child.package_id, child.parent_id, request_count)


def require_direct_child(expected_parent_id: str, stored_parent_id: str | None) -> None:
    if stored_parent_id != expected_parent_id:
        raise ValueError('specified packages are not a direct parent and child')
