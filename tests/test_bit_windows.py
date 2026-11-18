import base64
from contextlib import closing
from dataclasses import replace
import json
from hashlib import sha256
import sqlite3

from audit.archive import read_audit, source_check
from audit.compare import compare_audits
from capture.catalog import RecordingCatalog
from capture.recording import register_recording
from handover.format import decode_package, encode_package
from offline.accept import accept_package
from offline.corrections import ByteConflict, CorrectionRequest
from offline.settle import correct_package
from tests import BenchCase
from views.layout import ViewLayout
from views.registry import ViewRegistry, register_views

BANKS = {'P': bytes.fromhex('a3 5c e1'), 'Q': bytes.fromhex('a3 5c')}


def layouts():
    return (
        ViewLayout('WHOLE', 'P', 0, 1, 1, 2, 'big'),
        ViewLayout('LO', 'P', 0, 1, 1, 1, 'little', bit_start=0, bit_length=4),
        ViewLayout('BE8', 'P', 0, 1, 1, 2, 'big', bit_start=8, bit_length=1),
        ViewLayout('Q0', 'Q', 0, 1, 1, 2, 'little', bit_start=0, bit_length=1),
        ViewLayout('CROSS', 'P', 0, 1, 1, 2, 'big', bit_start=4, bit_length=8),
        ViewLayout('LE8', 'P', 0, 1, 1, 2, 'little', bit_start=8, bit_length=1),
        ViewLayout('LE0', 'P', 0, 1, 1, 2, 'little', bit_start=0, bit_length=1),
    )


class BitWindowTests(BenchCase):
    def prepare_windows(self):
        recording = register_recording(self.recordings, 'status-window', BANKS)
        register_views(self.recordings, self.registry, recording, layouts())
        return recording

    def handoff_windows(self):
        issued = self.publish(self.prepare_windows(), ('WHOLE', 'LO', 'BE8', 'Q0', 'CROSS', 'LE8', 'LE0'))
        self.disconnect_source()
        return issued, accept_package(self.offline, issued.wire)

    def values(self, package_id):
        return {view.name: view.values for view in read_audit(self.offline, package_id).views}

    def test_window_definition_validation(self):
        recording = self.prepare_windows()
        catalog = self.registry.get_catalog(recording)
        valid = replace(layouts()[2], name='EXTRA')
        for start, length in ((None, 1), (0, None), (True, 1), (0, 0), (16, 1), (-1, 1), (0, 17)):
            with self.subTest(start=start, length=length), self.assertRaises(ValueError):
                invalid = replace(layouts()[2], name='BAD', bit_start=start, bit_length=length)
                register_views(self.recordings, self.registry, recording, [valid, invalid])
        self.assertEqual(self.registry.get_catalog(recording), catalog)

    def test_clipped_payload_preserves_shared_positions(self):
        recording = self.prepare_windows()
        issued = self.publish(recording, ('WHOLE', 'CROSS', 'LE8', 'Q0'))
        payload = decode_package(issued.wire).payload
        self.assertEqual(payload.data, b'\xa3\x5c\xa3')
        by_name = {view.name: view for view in payload.views}
        self.assertEqual(by_name['WHOLE'].elements, ((0, 1),))
        self.assertEqual(by_name['CROSS'].elements, ((0, 1),))
        self.assertEqual(by_name['LE8'].elements, ((1,),))
        self.assertEqual(by_name['Q0'].elements, ((2,),))
        single = self.publish(recording, ('BE8',))
        self.assertEqual(decode_package(single.wire).payload.data, b'\xa3')
        self.disconnect_source()
        parent = accept_package(self.offline, issued.wire)
        self.assertEqual(self.values(parent), {
            'WHOLE': (0xA35C,), 'CROSS': (0x35,), 'LE8': (0,), 'Q0': (1,),
        })

    def test_cross_byte_window_correction(self):
        _, parent = self.handoff_windows()
        self.assertEqual(self.values(parent)['CROSS'], (0x35,))
        child, receipt = correct_package(self.offline, parent, [CorrectionRequest('CROSS', 0, 0x96)])
        self.assertEqual(self.values(child)['CROSS'], (0x96,))
        self.assertEqual(self.values(child)['WHOLE'], (0xA96C,))
        self.assertEqual(self.values(parent)['WHOLE'], (0xA35C,))
        deltas = {row.name: row.total_delta for row in compare_audits(self.offline, parent, child)}
        self.assertEqual(deltas['CROSS'], 0x96 - 0x35)
        self.reopen_offline()
        self.assertEqual(self.offline.get_receipt(child), receipt)
        self.assertEqual(self.values(child)['WHOLE'], (0xA96C,))

    def test_bit_level_conflict_and_unchanged_request(self):
        _, parent = self.handoff_windows()
        before = self.inventory()
        unchanged = CorrectionRequest('BE8', 0, 1)
        for order in ((unchanged, CorrectionRequest('LE0', 0, 0)),
                      (CorrectionRequest('LE0', 0, 0), unchanged)):
            with self.assertRaises(ByteConflict):
                correct_package(self.offline, parent, order)
        self.assertEqual(self.inventory(), before)

    def test_window_range_and_invalid_value(self):
        _, parent = self.handoff_windows()
        before = self.inventory()
        for name, value in (('BE8', -1), ('BE8', 2), ('BE8', True),
                            ('CROSS', -1), ('CROSS', 0x100), ('LO', 16)):
            with self.subTest(name=name, value=value), self.assertRaises(ValueError):
                correct_package(self.offline, parent, [CorrectionRequest(name, 0, value)])
        self.assertEqual(self.inventory(), before)

    def test_window_wire_roundtrip(self):
        issued, parent = self.handoff_windows()
        envelope = decode_package(issued.wire)
        self.assertEqual(encode_package(envelope), issued.wire)
        self.assertEqual(accept_package(self.offline, issued.wire), parent)

    def test_repeated_reference_and_unreferenced_payload_rejected(self):
        issued, parent = self.handoff_windows()
        for mutate in ('repeat', 'unreferenced'):
            outer = json.loads(issued.wire)
            view = next(item for item in outer['body']['views'] if item['name'] == 'CROSS')
            if mutate == 'repeat':
                view['elements'][0] = [view['elements'][0][0], view['elements'][0][0]]
            else:
                outer['body']['data'] = base64.b64encode(
                    base64.b64decode(outer['body']['data']) + b'\x00'
                ).decode('ascii')
            signed = {key: outer[key] for key in ('version', 'body')}
            outer['sha256'] = sha256(json.dumps(
                signed, sort_keys=True, separators=(',', ':')).encode('ascii')).hexdigest()
            with self.subTest(mutate=mutate), self.assertRaises(ValueError):
                accept_package(self.offline, json.dumps(outer).encode('ascii'))
        self.assertEqual(self.inventory(), (((parent, None),), ()))

    def test_window_requires_both_fields(self):
        issued, _ = self.handoff_windows()
        outer = json.loads(issued.wire)
        view = next(item for item in outer['body']['views'] if item['name'] == 'CROSS')
        del view['bit_length']
        signed = {key: outer[key] for key in ('version', 'body')}
        outer['sha256'] = sha256(json.dumps(
            signed, sort_keys=True, separators=(',', ':')).encode('ascii')).hexdigest()
        with self.assertRaises(ValueError):
            accept_package(self.offline, json.dumps(outer).encode('ascii'))

    def test_source_check_is_unsigned_window(self):
        recording = self.prepare_windows()
        self.assertEqual(source_check(self.recordings, self.registry, recording, 'CROSS').values, (0x35,))
        self.assertEqual(source_check(self.recordings, self.registry, recording, 'LE0').values, (1,))

    def test_legacy_database_gains_window_columns(self):
        legacy_path = self.root / 'legacy.sqlite'
        with closing(sqlite3.connect(legacy_path)) as legacy:
            legacy.executescript('''
                CREATE TABLE recordings (
                    recording_id TEXT PRIMARY KEY,
                    external_name TEXT NOT NULL UNIQUE,
                    fingerprint TEXT NOT NULL
                );
                CREATE TABLE recording_banks (
                    recording_id TEXT NOT NULL REFERENCES recordings(recording_id),
                    bank_name TEXT NOT NULL,
                    data BLOB NOT NULL CHECK (length(data) > 0),
                    PRIMARY KEY (recording_id, bank_name)
                );
                CREATE TABLE view_layouts (
                    recording_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    bank_name TEXT NOT NULL,
                    start_byte INTEGER NOT NULL,
                    stride_hex TEXT NOT NULL,
                    element_count INTEGER NOT NULL,
                    width INTEGER NOT NULL,
                    byteorder TEXT NOT NULL,
                    PRIMARY KEY (recording_id, name),
                    FOREIGN KEY (recording_id, bank_name)
                        REFERENCES recording_banks(recording_id, bank_name)
                );
                INSERT INTO recordings VALUES ('rec-old', 'old', 'x');
                INSERT INTO recording_banks VALUES ('rec-old', 'P', X'A35C');
                INSERT INTO view_layouts VALUES ('rec-old', 'A', 'P', 0, '0x1', 1, 2, 'little');
            ''')
        with closing(sqlite3.connect(legacy_path)) as connection:
            recordings, registry = RecordingCatalog(connection), ViewRegistry(connection)
            recordings.initialize()
            registry.initialize()
            original = ViewLayout('A', 'P', 0, 1, 1, 2, 'little')
            self.assertEqual(registry.get_catalog('rec-old'), (original,))
            self.assertEqual(register_views(recordings, registry, 'rec-old', [original]), (original,))
            window = ViewLayout('W', 'P', 0, 1, 1, 2, 'big', bit_start=8, bit_length=1)
            register_views(recordings, registry, 'rec-old', [window])
            self.assertEqual(source_check(recordings, registry, 'rec-old', 'W').values, (1,))
            self.assertEqual(source_check(recordings, registry, 'rec-old', 'A').values, (0x5CA3,))
