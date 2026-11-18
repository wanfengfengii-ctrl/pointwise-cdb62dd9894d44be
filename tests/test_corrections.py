from audit.archive import read_audit
from audit.compare import compare_audits
from audit.totals import ViewTotals
from offline.accept import accept_package
from offline.corrections import ByteConflict, CorrectionRequest
from offline.settle import correct_package
from tests import BenchCase


class CorrectionTests(BenchCase):
    def test_shared_byte_update(self):
        parent = self.handoff()
        original = read_audit(self.offline, parent)
        child, receipt = correct_package(self.offline, parent, [CorrectionRequest('A', 0, 1025)])
        revised = read_audit(self.offline, child)
        self.assertEqual(tuple(view.values for view in revised.views), ((1025,), (1027,), (513,)))
        self.assertEqual(tuple(view.values for view in original.views), ((513,), (515,), (513,)))
        self.assertEqual(read_audit(self.offline, parent), original)
        self.assertEqual((receipt.parent_id, receipt.child_id, receipt.request_count), (parent, child, 1))
        self.assertEqual(self.offline.get_receipt(child), receipt)
        comparison = compare_audits(self.offline, parent, child)
        self.assertEqual(tuple(row.name for row in comparison), ('A', 'B', 'C'))
        self.assertEqual(tuple(row.total_delta for row in comparison), (512, 512, 0))
        self.assertEqual(comparison[1].parent.totals, ViewTotals(1, 515, 515, 515))
        self.assertEqual(comparison[1].child.totals, ViewTotals(1, 1027, 1027, 1027))
        self.reopen_offline()
        self.assertEqual(read_audit(self.offline, parent), original)
        self.assertEqual(read_audit(self.offline, child), revised)

    def test_consistent_batch_both_orders(self):
        parent = self.handoff()
        requests = (CorrectionRequest('A', 0, 1025), CorrectionRequest('B', 0, 1027))
        expected = ((1025,), (1027,), (513,))
        audits = []
        for order in (requests, requests[::-1]):
            child, receipt = correct_package(self.offline, parent, iter(order))
            views = read_audit(self.offline, child).views
            self.assertEqual(tuple(view.values for view in views), expected)
            self.assertEqual(receipt.request_count, 2)
            audits.append(views)
        self.assertEqual(audits[0], audits[1])
        self.assertEqual(tuple(view.values[0] for view in read_audit(self.offline, parent).views), (513, 515, 513))

    def test_internal_overlap_and_reverse_mixed_width(self):
        parent = self.handoff(('O', 'R', 'M'))
        original = read_audit(self.offline, parent)
        self.assertEqual(tuple(view.values for view in original.views), ((513, 770), (770, 513), (2,)))
        child, _ = correct_package(self.offline, parent, [CorrectionRequest('O', 0, 1025)])
        expected = ((1025, 772), (772, 1025), (4,))
        self.assertEqual(tuple(view.values for view in read_audit(self.offline, child).views), expected)
        requests = (CorrectionRequest('R', 0, 772), CorrectionRequest('O', 1, 772), CorrectionRequest('M', 0, 4))
        for order in (requests, requests[::-1]):
            coalesced, _ = correct_package(self.offline, parent, order)
            self.assertEqual(tuple(view.values for view in read_audit(self.offline, coalesced).views), expected)
        before = self.inventory()
        conflict = (CorrectionRequest('O', 0, 1025), CorrectionRequest('O', 1, 773))
        for order in (conflict, conflict[::-1]):
            with self.assertRaises(ByteConflict):
                correct_package(self.offline, parent, order)
        self.assertEqual(self.inventory(), before)
        self.assertEqual(read_audit(self.offline, parent), original)

    def test_shared_byte_conflict(self):
        parent = self.handoff()
        before = self.inventory()
        batch = (CorrectionRequest('A', 0, 1025), CorrectionRequest('B', 0, 1283))
        for order in (batch, batch[::-1]):
            with self.subTest(order=order), self.assertRaises(ByteConflict):
                correct_package(self.offline, parent, order)
            self.assertEqual(self.inventory(), before)
        self.assertEqual(tuple(view.values[0] for view in read_audit(self.offline, parent).views), (513, 515, 513))

    def test_invalid_request_does_not_leave_results(self):
        parent = self.handoff()
        before, original = self.inventory(), read_audit(self.offline, parent)
        valid = CorrectionRequest('A', 0, 1025)
        for invalid in (CorrectionRequest('B', 1, 3), CorrectionRequest('B', -1, 3),
                        CorrectionRequest('B', 0, 65536), CorrectionRequest('B', 0, True),
                        {'view_name': 'B'}):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                correct_package(self.offline, parent, [valid, invalid])
        with self.assertRaises(ValueError):
            correct_package(self.offline, parent, [])
        with self.assertRaises(KeyError):
            correct_package(self.offline, parent, [valid, CorrectionRequest('missing', 0, 1)])
        with self.assertRaises(KeyError):
            correct_package(self.offline, 'missing', [valid])
        self.assertEqual(self.inventory(), before)
        self.assertEqual(read_audit(self.offline, parent), original)

    def test_comparison_requires_direct_parent(self):
        recording = self.prepare()
        first = self.publish(recording, ('A', 'B', 'C'))
        alternate = self.publish(recording, ('C', 'B', 'A'))
        self.disconnect_source()
        parent = accept_package(self.offline, first.wire)
        other = accept_package(self.offline, alternate.wire)
        child, _ = correct_package(self.offline, parent, [CorrectionRequest('A', 0, 1025)])
        grandchild, _ = correct_package(self.offline, child, [CorrectionRequest('A', 0, 513)])
        with self.assertRaisesRegex(ValueError, 'direct parent'):
            compare_audits(self.offline, other, child)
        with self.assertRaisesRegex(ValueError, 'direct parent'):
            compare_audits(self.offline, parent, grandchild)
        with self.assertRaises(KeyError):
            compare_audits(self.offline, parent, 'missing')
        self.assertEqual([(row.name, row.total_delta) for row in compare_audits(self.offline, parent, child)],
                         [('A', 512), ('B', 512), ('C', 0)])
        self.assertEqual([row.total_delta for row in compare_audits(self.offline, child, grandchild)], [-512, -512, 0])

    def test_failed_commit_and_reopen(self):
        parent = self.handoff()
        child, receipt = correct_package(self.offline, parent, [CorrectionRequest('A', 0, 1025)])
        before = self.inventory()
        original = read_audit(self.offline, parent)
        revised = read_audit(self.offline, child)
        self.assertEqual(tuple(view.values[0] for view in revised.views), (1025, 1027, 513))

        def fail_commit():
            raise OSError('sample final write refused')

        with self.assertRaisesRegex(OSError, 'final write refused'):
            correct_package(self.offline, parent, [CorrectionRequest('C', 0, 7)], before_commit=fail_commit)
        self.assertEqual(self.inventory(), before)
        self.reopen_offline()
        self.assertEqual(self.inventory(), before)
        self.assertEqual(read_audit(self.offline, parent), original)
        self.assertEqual(read_audit(self.offline, child), revised)
        self.assertEqual(self.offline.get_receipt(child), receipt)
        with self.assertRaises(KeyError):
            self.offline.get_receipt(parent)
