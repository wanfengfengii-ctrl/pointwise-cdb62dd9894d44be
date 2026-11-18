from contextlib import closing
import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory

from audit.archive import read_audit, source_check
from audit.compare import compare_audits
from capture.catalog import RecordingCatalog
from capture.recording import register_recording
from handover.format import decode_package
from handover.issue import issue_package
from handover.issued_index import IssuedIndex
from offline.accept import accept_package
from offline.corrections import ByteConflict, CorrectionRequest
from offline.revisions import RevisionStore
from offline.settle import correct_package
from views.layout import ViewLayout
from views.registry import ViewRegistry, register_views


def load_sample() -> dict:
    return json.loads((Path(__file__).resolve().parent / 'examples' / 'bench.json').read_text(encoding='utf-8'))


def prepare_sample(recordings: RecordingCatalog, registry: ViewRegistry, sample: dict) -> str:
    banks = {name: bytes(values) for name, values in sample['banks'].items()}
    recording = register_recording(recordings, sample['recording'], banks)
    register_views(recordings, registry, recording, (ViewLayout(**row) for row in sample['views']))
    return recording


def _scenario(case_id, inputs, expected, actual, downstream_expected, downstream_actual, paths, oracle):
    if actual != expected or downstream_actual != downstream_expected:
        marker = 'SHARED_BYTE_SETTLEMENT_MISMATCH' if case_id in ('n6', 'n7') else 'HANDOVER_MISMATCH'
        raise SystemExit(f'{marker} {case_id} actual={actual!r} downstream={downstream_actual!r}')
    result = {
        'case_id': case_id,
        'input': inputs,
        'expected': expected,
        'actual': actual,
        'downstream_expected': downstream_expected,
        'downstream_actual': downstream_actual,
        'code_paths': paths,
        'oracle': oracle,
    }
    print('POINTWISE_SCENARIO ' + json.dumps(result, sort_keys=True), flush=True)


def _counts(connection):
    revisions = connection.execute('SELECT count(*) FROM revisions').fetchone()[0]
    receipts = connection.execute('SELECT count(*) FROM correction_receipts').fetchone()[0]
    return [revisions, receipts]


WINDOW_BANKS = {'P': bytes.fromhex('a3 5c e1'), 'Q': bytes.fromhex('a3 5c')}
WINDOW_VIEWS = (
    ViewLayout('WHOLE', 'P', 0, 1, 1, 2, 'big'),
    ViewLayout('LO', 'P', 0, 1, 1, 1, 'little', bit_start=0, bit_length=4),
    ViewLayout('BE8', 'P', 0, 1, 1, 2, 'big', bit_start=8, bit_length=1),
    ViewLayout('Q0', 'Q', 0, 1, 1, 2, 'little', bit_start=0, bit_length=1),
    ViewLayout('CROSS', 'P', 0, 1, 1, 2, 'big', bit_start=4, bit_length=8),
    ViewLayout('LE8', 'P', 0, 1, 1, 2, 'little', bit_start=8, bit_length=1),
    ViewLayout('LE0', 'P', 0, 1, 1, 2, 'little', bit_start=0, bit_length=1),
)
WINDOW_SELECTION = ('WHOLE', 'CROSS', 'BE8', 'LE0', 'Q0')


def _window_demo(store: RevisionStore, connection, issued) -> None:
    payload = decode_package(issued.wire).payload
    parent_id = accept_package(store, issued.wire)
    parent = read_audit(store, parent_id)
    _scenario(
        'w1', {'selection': WINDOW_SELECTION, 'banks': {'P': WINDOW_BANKS['P'].hex(), 'Q': WINDOW_BANKS['Q'].hex()}},
        'a35ca3', payload.data.hex(), [0xA35C, 0x35, 1, 1, 1],
        [view.values[0] for view in parent.views],
        ['handover/project.py', 'handover/payload.py', 'audit/readings.py'],
        'Only A3 5C from P and A3 from Q are carried; CROSS shares the first two P bytes.',
    )
    child_id, receipt = correct_package(store, parent_id, [CorrectionRequest('CROSS', 0, 0x96)])
    child = read_audit(store, child_id)
    deltas = {row.name: row.total_delta for row in compare_audits(store, parent_id, child_id)}
    _scenario(
        'w2', {'view': 'CROSS', 'index': 0, 'value': 0x96},
        [0xA96C, 0x96, 1, 1, 1], [view.values[0] for view in child.views],
        {'deltas': {'CROSS': 0x96 - 0x35}, 'parent': [0xA35C, 0x35, 1, 1, 1]},
        {'deltas': {'CROSS': deltas['CROSS']},
         'parent': [view.values[0] for view in read_audit(store, parent_id).views]},
        ['offline/corrections.py', 'offline/settle.py', 'audit/compare.py'],
        'The 8-bit window spans P bytes 0 and 1; writing 96 yields A9 6C for the whole word.',
    )
    before = _counts(connection)
    outcomes = []
    unchanged = CorrectionRequest('BE8', 0, 1)
    for order in ((unchanged, CorrectionRequest('LE0', 0, 0)),
                  (CorrectionRequest('LE0', 0, 0), unchanged)):
        try:
            correct_package(store, parent_id, order)
        except ByteConflict:
            outcomes.append('rejected')
        else:
            outcomes.append('issued')
    _scenario(
        'w3', {'batch': ['BE8=1 (unchanged)', 'LE0=0'], 'both_orders': True},
        ['rejected', 'rejected'], outcomes, [0, 0],
        [end - start for start, end in zip(before, _counts(connection), strict=True)],
        ['offline/corrections.py', 'offline/settle.py', 'offline/revisions.py'],
        'BE8 is P byte 0 bit 0 in big-endian order; LE0 is P byte 0 bit 0 in little-endian order.',
    )
    if (read_audit(store, parent_id), read_audit(store, child_id), store.get_receipt(child_id)) != (
        parent, child, receipt,
    ):
        raise SystemExit('WINDOW_REPLAY_MISMATCH')
    print(f'位窗断源更正 父件 {parent_id} 子件 {child_id}，裁剪载荷 {payload.data.hex()}，'
          f'回执请求数 {receipt.request_count}')
    return parent_id, child_id, parent, child, receipt


def main() -> None:
    sample = load_sample()
    names = sample['selection']
    with TemporaryDirectory(prefix='bench-handover-') as scratch:
        root = Path(scratch)
        source_path = root / 'source.sqlite'
        offline_path = root / 'offline.sqlite'
        with closing(sqlite3.connect(source_path)) as source:
            recordings, registry, index = RecordingCatalog(source), ViewRegistry(source), IssuedIndex(source)
            recordings.initialize()
            registry.initialize()
            index.initialize()
            recording = prepare_sample(recordings, registry, sample)
            source_values = [source_check(recordings, registry, recording, name).values[0] for name in names]
            issued = issue_package(recordings, registry, index, recording, names)
            window_recording = register_recording(recordings, 'status-window', WINDOW_BANKS)
            register_views(recordings, registry, window_recording, WINDOW_VIEWS)
            window_issued = issue_package(
                recordings, registry, index, window_recording, WINDOW_SELECTION,
            )
        source_path.rename(root / 'disconnected.sqlite')
        with closing(sqlite3.connect(offline_path)) as connection:
            store = RevisionStore(connection)
            store.initialize()
            window_parent_id, window_child_id, window_parent, window_child, window_receipt = _window_demo(
                store, connection, window_issued,
            )
            parent_id = accept_package(store, issued.wire)
            parent = read_audit(store, parent_id)
            parent_values = [view.values[0] for view in parent.views]
            _scenario(
                'n4', {'selection': names, 'banks': sample['banks']},
                [513, 515, 513], source_values, [513, 515, 513], parent_values,
                ['audit/archive.py', 'handover/issue.py', 'offline/accept.py'],
                'Read 01 02 as little endian, 02 03 as big endian, and Q independently.',
            )
            child_id, receipt = correct_package(store, parent_id, [CorrectionRequest('A', 0, 1025)])
            child = read_audit(store, child_id)
            differences = compare_audits(store, parent_id, child_id)
            _scenario(
                'n6', {'view': 'A', 'index': 0, 'value': 1025},
                [1025, 1027, 513], [view.values[0] for view in child.views],
                {'deltas': [512, 512, 0], 'parent': [513, 515, 513]},
                {'deltas': [row.total_delta for row in differences],
                 'parent': [view.values[0] for view in read_audit(store, parent_id).views]},
                ['handover/project.py', 'offline/corrections.py', 'audit/compare.py'],
                'A encodes as 01 04. B reads 04 03 in big endian. Q byte 1 stays 02.',
            )
            batch = (CorrectionRequest('A', 0, 1025), CorrectionRequest('B', 0, 1283))
            before = _counts(connection)
            outcomes = []
            for order in (batch, batch[::-1]):
                try:
                    correct_package(store, parent_id, order)
                except ByteConflict:
                    outcomes.append('rejected')
                else:
                    outcomes.append('issued')
            after = _counts(connection)
            _scenario(
                'n7', {'batch': [request.__dict__ for request in batch], 'both_orders': True},
                ['rejected', 'rejected'], outcomes, [0, 0],
                [end - start for start, end in zip(before, after, strict=True)],
                ['offline/corrections.py', 'offline/settle.py', 'offline/revisions.py'],
                'The same P byte would need both 04 and 05. Neither order may commit.',
            )
        with closing(sqlite3.connect(offline_path)) as connection:
            store = RevisionStore(connection)
            store.initialize()
            if (read_audit(store, parent_id), read_audit(store, child_id), store.get_receipt(child_id)) != (
                parent, child, receipt,
            ):
                raise SystemExit('HANDOVER_REPLAY_MISMATCH')
            if (read_audit(store, window_parent_id), read_audit(store, window_child_id),
                    store.get_receipt(window_child_id)) != (
                window_parent, window_child, window_receipt,
            ):
                raise SystemExit('WINDOW_REPLAY_MISMATCH')
            window_deltas = [row.total_delta for row in compare_audits(store, window_parent_id, window_child_id)]
            if window_deltas != [0xA96C - 0xA35C, 0x96 - 0x35, 0, 0, 0]:
                raise SystemExit(f'WINDOW_REPLAY_MISMATCH deltas={window_deltas!r}')
            print(f'复领父件 {parent_id} 与子件 {child_id}，回执请求数 {receipt.request_count}')
            print(f'复领位窗父件 {window_parent_id} 与子件 {window_child_id}，'
                  f'回执请求数 {window_receipt.request_count}，差账 {window_deltas}')


if __name__ == '__main__':
    main()
