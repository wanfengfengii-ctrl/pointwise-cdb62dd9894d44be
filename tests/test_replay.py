import sqlite3

from audit.archive import read_audit
from offline.accept import accept_package
from offline.corrections import CorrectionRequest
from offline.settle import correct_package
from tests import BenchCase


LEGACY_WIRE = (
    b'{"version":1,"body":{"id":"bench-legacy-001","recording":"bench-legacy","views":['
    b'{"name":"X","width":2,"byteorder":"little","data":"AQI="},'
    b'{"name":"Y","width":2,"byteorder":"big","data":"AgM="}]},'
    b'"sha256":"5a1edd61ac44cb3e7beb604f603478537024a04d8c4c58f44c0c8acd1c64a560"}'
)


class ReplayTests(BenchCase):
    def test_legacy_inline_package_preserves_independent_bytes(self):
        self.disconnect_source()
        parent = accept_package(self.offline, LEGACY_WIRE)
        self.assertEqual(parent, 'bench-legacy-001')
        self.assertEqual(tuple(view.values[0] for view in read_audit(self.offline, parent).views), (513, 515))
        child, receipt = correct_package(self.offline, parent, [CorrectionRequest('X', 0, 1025)])
        self.reopen_offline()
        self.assertEqual(accept_package(self.offline, LEGACY_WIRE), parent)
        self.assertEqual(tuple(view.values[0] for view in read_audit(self.offline, child).views), (1025, 515))
        self.assertEqual(self.offline.get_receipt(child), receipt)
        self.assertEqual(tuple(view.values[0] for view in read_audit(self.offline, parent).views), (513, 515))

    def test_receipt_write_failure_is_atomic(self):
        parent = self.handoff()
        child, receipt = correct_package(self.offline, parent, [CorrectionRequest('A', 0, 1025)])
        before = self.inventory()
        self.offline_db.execute('''
            CREATE TEMP TRIGGER refuse_second_receipt BEFORE INSERT ON correction_receipts
            BEGIN SELECT RAISE(ABORT, 'receipt write refused'); END
        ''')
        with self.assertRaisesRegex(sqlite3.IntegrityError, 'receipt write refused'):
            correct_package(self.offline, parent, [CorrectionRequest('C', 0, 7)])
        self.reopen_offline()
        self.assertEqual(self.inventory(), before)
        self.assertEqual(self.offline.get_receipt(child), receipt)
        self.assertEqual(tuple(view.values[0] for view in read_audit(self.offline, child).views), (1025, 1027, 513))

    def test_initialization_replay(self):
        parent = self.handoff()
        child, receipt = correct_package(self.offline, parent, [CorrectionRequest('A', 0, 1025)])
        records = {key: self.offline.get(key) for key in (parent, child)}
        audits = {key: read_audit(self.offline, key) for key in records}
        before = self.inventory()
        self.reopen_offline()
        self.offline.initialize()
        self.assertEqual(self.inventory(), before)
        for package_id in records:
            self.assertEqual(self.offline.get(package_id), records[package_id])
            self.assertEqual(read_audit(self.offline, package_id), audits[package_id])
        self.assertEqual(self.offline.get(child).parent_id, parent)
        self.assertEqual(self.offline.get_receipt(child), receipt)
        newer, newer_receipt = correct_package(self.offline, child, [CorrectionRequest('C', 0, 7)])
        self.assertEqual(self.offline.get(newer).parent_id, child)
        self.assertEqual(self.offline.get_receipt(newer), newer_receipt)
        self.assertEqual(tuple(view.values[0] for view in read_audit(self.offline, newer).views), (1025, 1027, 7))
