from handover.format import decode_package
from offline.revisions import RevisionStore


def accept_package(store: RevisionStore, wire: bytes) -> str:
    package = decode_package(wire)
    return store.store_import(package, wire)
