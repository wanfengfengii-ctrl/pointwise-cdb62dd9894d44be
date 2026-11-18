from collections.abc import Iterable, Mapping

from views.integers import validate_integer_format
from views.layout import ViewLayout, covered_bounds
from views.windows import normalize_bit_window


def validate_view_batch(
    layouts: Iterable[ViewLayout], lengths: Mapping[str, int],
) -> tuple[ViewLayout, ...]:
    try:
        batch = tuple(layouts)
    except TypeError as error:
        raise ValueError('view batch must be iterable') from error
    if not batch:
        raise ValueError('view batch is empty')
    names = set()
    for view in batch:
        if not isinstance(view, ViewLayout):
            raise ValueError('view definition must be a ViewLayout')
        if not isinstance(view.name, str) or not view.name.strip():
            raise ValueError('view name must be a nonempty string')
        view.name.encode('utf-8')
        if view.name in names:
            raise ValueError(f'duplicate view {view.name!r} in batch')
        names.add(view.name)
        if not isinstance(view.bank_name, str) or view.bank_name not in lengths:
            raise ValueError(f'view {view.name!r} has an unknown bank')
        validate_integer_format(view.width, view.byteorder)
        if any(type(value) is not int for value in (view.start, view.stride, view.count)):
            raise ValueError('start, stride and count must be integers')
        if view.stride == 0 or view.count < 1:
            raise ValueError('stride must be nonzero and count must be positive')
        normalize_bit_window(view.width, view.byteorder, view.bit_start, view.bit_length)
        lower, upper = covered_bounds(view)
        if lower < 0 or upper > lengths[view.bank_name]:
            raise ValueError(f'view {view.name!r} extends outside its bank')
    return batch
