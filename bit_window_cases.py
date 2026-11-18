"""Run the public handoff examples after implementing bit windows."""
import unittest
from dataclasses import replace

from audit.archive import read_audit, source_check
from audit.compare import compare_audits
from capture.recording import register_recording
from handover.format import decode_package
from offline.accept import accept_package
from offline.corrections import ByteConflict, CorrectionRequest
from offline.settle import correct_package
from tests import BenchCase
from views.layout import ViewLayout
from views.registry import register_views


BANKS = {"P": bytes.fromhex("a3 5c e1"), "Q": bytes.fromhex("a3 5c")}
NAMES = ("WHOLE", "LO", "BE8", "Q0", "REV", "CROSS", "HI", "LE8", "LE0")
ORIGINAL = ((0xA35C,), (3,), (1,), (1,), (0, 1), (0x35,), (10,), (0,), (1,))
NIBBLES = ((0x565C,), (6,), (0,), (1,), (0, 0), (0x65,), (5,), (0,), (0,))
NIBBLE_DELTAS = (-0x4D00, 3, -1, 0, -1, 0x30, -5, 0, -1)


def layouts():
    return (
        ViewLayout("WHOLE", "P", 0, 1, 1, 2, "big"),
        ViewLayout("LO", "P", 0, 1, 1, 1, "little", bit_start=0, bit_length=4),
        ViewLayout("BE8", "P", 0, 1, 1, 2, "big", bit_start=8, bit_length=1),
        ViewLayout("Q0", "Q", 0, 1, 1, 2, "little", bit_start=0, bit_length=1),
        ViewLayout("REV", "P", 1, -1, 2, 2, "big", bit_start=8, bit_length=1),
        ViewLayout("CROSS", "P", 0, 1, 1, 2, "big", bit_start=4, bit_length=8),
        ViewLayout("HI", "P", 0, 1, 1, 1, "little", bit_start=4, bit_length=4),
        ViewLayout("LE8", "P", 0, 1, 1, 2, "little", bit_start=8, bit_length=1),
        ViewLayout("LE0", "P", 0, 1, 1, 2, "little", bit_start=0, bit_length=1),
    )


class BitWindowCases(BenchCase):
    def prepare_windows(self):
        recording = register_recording(self.recordings, "status-word", BANKS)
        register_views(self.recordings, self.registry, recording, layouts())
        return recording

    def handoff_windows(self):
        recording = self.prepare_windows()
        issued = self.publish(recording, NAMES)
        self.disconnect_source()
        return accept_package(self.offline, issued.wire)

    def values(self, package_id):
        return {view.name: view.values for view in read_audit(self.offline, package_id).views}

    def test_fixed_registration_and_invalid_window(self):
        recording = self.prepare_windows()
        original = self.registry.get_catalog(recording)
        self.source_db.close()
        self.open_source()
        self.assertEqual(register_views(self.recordings, self.registry, recording, layouts()), original)
        whole, _, be8, *_ = layouts()
        with self.assertRaises(ValueError):
            register_views(self.recordings, self.registry, recording, [replace(be8, bit_start=9)])
        for start, length in ((None, 1), (0, None), (True, 1), (0, 0), (15, 2)):
            with self.subTest(start=start, length=length), self.assertRaises(ValueError):
                valid = replace(whole, name="EXTRA")
                invalid = replace(be8, name="INVALID", bit_start=start, bit_length=length)
                register_views(self.recordings, self.registry, recording, [valid, invalid])
        self.assertEqual(self.registry.get_catalog(recording), original)
        self.assertEqual(source_check(self.recordings, self.registry, recording, "REV").values, (0, 1))

    def test_clipped_byte_and_mixed_selection(self):
        recording = self.prepare_windows()
        source = tuple(source_check(self.recordings, self.registry, recording, name) for name in NAMES)
        self.assertEqual(tuple(view.values for view in source), ORIGINAL)
        single = self.publish(recording, ("BE8",))
        mixed = self.publish(recording, NAMES)
        self.assertEqual(self.publish(recording, NAMES), mixed)
        self.assertEqual(decode_package(single.wire).payload.data, b"\xa3")
        self.assertEqual(sorted(decode_package(mixed.wire).payload.data), [0x5C, 0xA3, 0xA3])
        self.disconnect_source()
        parent = accept_package(self.offline, single.wire)
        self.assertEqual(self.values(parent), {"BE8": (1,)})
        child, _ = correct_package(self.offline, parent, [CorrectionRequest("BE8", 0, 0)])
        self.assertEqual(self.values(child), {"BE8": (0,)})
        self.assertEqual(self.offline.get(child).package.payload.data, b"\xa2")
        mixed_parent = accept_package(self.offline, mixed.wire)
        self.assertEqual(read_audit(self.offline, mixed_parent).views, source)

    def test_shared_writes_and_fixed_receipt(self):
        parent = self.handoff_windows()
        pair = (CorrectionRequest("HI", 0, 5), CorrectionRequest("LO", 0, 6))
        for order in (pair, pair[::-1]):
            child, receipt = correct_package(self.offline, parent, iter(order))
            self.assertEqual(tuple(self.values(child).items()), tuple(zip(NAMES, NIBBLES, strict=True)))
        self.assertEqual((receipt.child_id, receipt.parent_id, receipt.request_count), (child, parent, 2))
        child_audit = read_audit(self.offline, child)
        self.reopen_offline()
        self.assertEqual(self.offline.get_receipt(child), receipt)
        self.assertEqual(read_audit(self.offline, child), child_audit)
        self.assertEqual(tuple(self.values(parent).items()), tuple(zip(NAMES, ORIGINAL, strict=True)))
        self.assertEqual(tuple(row.total_delta for row in compare_audits(self.offline, parent, child)), NIBBLE_DELTAS)
        for requests, expected in (
            ([CorrectionRequest("HI", 0, 5)], 0x535C),
            ([CorrectionRequest("CROSS", 0, 0x96)], 0xA96C),
            ([CorrectionRequest("BE8", 0, 0), CorrectionRequest("LE8", 0, 1)], 0xA25D),
            ([CorrectionRequest("WHOLE", 0, 0xA25D), CorrectionRequest("LE8", 0, 1)], 0xA25D),
        ):
            updated, _ = correct_package(self.offline, parent, requests)
            self.assertEqual(self.values(updated)["WHOLE"], (expected,))

    def test_conflict_independent_bank_and_rollback(self):
        parent = self.handoff_windows()
        before = self.inventory()
        unchanged = CorrectionRequest("BE8", 0, 1)
        for opposed in (CorrectionRequest("LE0", 0, 0), CorrectionRequest("WHOLE", 0, 0xA25C)):
            pair = (unchanged, opposed)
            for order in (pair, pair[::-1]):
                with self.assertRaises(ByteConflict):
                    correct_package(self.offline, parent, order)
        for value in (-1, 2, True):
            with self.assertRaises(ValueError):
                correct_package(self.offline, parent, [CorrectionRequest("BE8", 0, value)])
        self.assertEqual(self.inventory(), before)

        def refuse():
            raise OSError("sample commit refused")

        independent = (unchanged, CorrectionRequest("Q0", 0, 0))
        with self.assertRaisesRegex(OSError, "sample commit refused"):
            correct_package(self.offline, parent, independent, before_commit=refuse)
        self.reopen_offline()
        self.assertEqual(self.inventory(), before)
        child, receipt = correct_package(self.offline, parent, independent)
        self.reopen_offline()
        self.assertEqual(self.offline.get_receipt(child), receipt)
        self.assertEqual(self.values(child)["WHOLE"], (0xA35C,))
        self.assertEqual(self.values(child)["Q0"], (0,))
        self.assertEqual(self.values(parent)["Q0"], (1,))


if __name__ == "__main__":
    unittest.main()
