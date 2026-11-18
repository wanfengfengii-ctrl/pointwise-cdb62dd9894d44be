from collections.abc import Iterable, Mapping, Set
from dataclasses import dataclass

from views.layout import ViewLayout


@dataclass(frozen=True)
class ResolvedSelection:
    recording_id: str
    views: tuple[ViewLayout, ...]

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(view.name for view in self.views)


def resolve_selection(
    recording_id: str, catalog: Iterable[ViewLayout], names: Iterable[str],
) -> ResolvedSelection:
    if isinstance(names, (str, bytes, Mapping, Set)):
        raise ValueError('selection must be an ordered iterable of view names')
    try:
        ordered = tuple(names)
    except TypeError as error:
        raise ValueError('selection must be an ordered iterable of view names') from error
    if not ordered or any(not isinstance(name, str) or not name.strip() for name in ordered):
        raise ValueError('selection must contain nonempty view names')
    if len(set(ordered)) != len(ordered):
        raise ValueError('selection contains a duplicate view')
    by_name = {view.name: view for view in catalog}
    return ResolvedSelection(recording_id, tuple(by_name[name] for name in ordered))
