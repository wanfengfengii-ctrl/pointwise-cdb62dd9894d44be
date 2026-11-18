from dataclasses import dataclass

from audit.archive import AuditedView, read_audit
from audit.totals import sum_delta
from offline.lineage import require_direct_child
from offline.revisions import RevisionStore


@dataclass(frozen=True)
class ViewComparison:
    name: str
    parent: AuditedView
    child: AuditedView
    total_delta: int


def compare_audits(store: RevisionStore, parent_id: str, child_id: str) -> tuple[ViewComparison, ...]:
    parent = read_audit(store, parent_id)
    child = read_audit(store, child_id)
    require_direct_child(parent.package_id, child.parent_id)
    return tuple(
        ViewComparison(before.name, before, after, sum_delta(before.totals, after.totals))
        for before, after in zip(parent.views, child.views, strict=True)
    )
