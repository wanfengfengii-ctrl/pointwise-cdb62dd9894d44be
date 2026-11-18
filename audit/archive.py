from dataclasses import dataclass

from audit.readings import read_package_values, read_source_values
from audit.totals import ViewTotals, summarize_values
from capture.catalog import RecordingCatalog
from offline.revisions import RevisionStore
from views.registry import ViewRegistry


@dataclass(frozen=True)
class AuditedView:
    name: str
    values: tuple[int, ...]
    totals: ViewTotals


@dataclass(frozen=True)
class AuditRecord:
    package_id: str
    parent_id: str | None
    views: tuple[AuditedView, ...]


def _audited_view(name: str, values: tuple[int, ...]) -> AuditedView:
    return AuditedView(name, values, summarize_values(values))


def source_check(
    recordings: RecordingCatalog,
    registry: ViewRegistry,
    recording_id: str,
    view_name: str,
) -> AuditedView:
    recording = recordings.get(recording_id)
    for view in registry.get_catalog(recording_id):
        if view.name == view_name:
            return _audited_view(view.name, read_source_values(recording, view))
    raise KeyError(view_name)


def read_audit(store: RevisionStore, package_id: str) -> AuditRecord:
    revision = store.get(package_id)
    payload = revision.package.payload
    views = tuple(
        _audited_view(view.name, read_package_values(payload, view))
        for view in payload.views
    )
    return AuditRecord(revision.package_id, revision.parent_id, views)
