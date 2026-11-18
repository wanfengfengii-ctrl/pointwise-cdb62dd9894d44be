from audit.archive import source_check
from audit.totals import ViewTotals
from capture.banks import read_bank
from capture.recording import register_recording
from tests import BenchCase
from views.layout import ViewLayout
from views.registry import register_views


class RecordingTests(BenchCase):
    def test_decode_reverse_view(self):
        recording = register_recording(self.recordings, 'reverse', {'P': bytes([1, 2, 3])})
        view = ViewLayout('REV', 'P', 2, -1, 3, 1, 'big')
        register_views(self.recordings, self.registry, recording, [view])
        audit = source_check(self.recordings, self.registry, recording, 'REV')
        self.assertEqual(audit.values, (3, 2, 1))
        self.assertEqual(audit.totals, ViewTotals(3, 6, 1, 3))

    def test_reverse_two_byte_exact_summary(self):
        recording = register_recording(self.recordings, 'wide', {'P': bytes([0, 0, 2, 0, 255, 255])})
        view = ViewLayout('WIDE', 'P', 4, -2, 3, 2, 'little')
        register_views(self.recordings, self.registry, recording, [view])
        audit = source_check(self.recordings, self.registry, recording, 'WIDE')
        self.assertEqual(audit.values, (65535, 2, 0))
        self.assertEqual(audit.totals, ViewTotals(3, 65537, 0, 65535))

    def test_duplicate_recording(self):
        original = bytes([1, 2, 3])
        recording = register_recording(self.recordings, 'sample', {'P': original})
        self.assertEqual(register_recording(self.recordings, 'sample', {'P': original}), recording)
        with self.assertRaisesRegex(ValueError, 'different banks'):
            register_recording(self.recordings, 'sample', {'P': bytes([1, 2, 4])})
        self.assertEqual(self.recordings.find_by_name('sample').recording_id, recording)
        self.assertEqual(read_bank(self.recordings.get(recording).banks, 'P'), original)

    def test_replay_preserves_name_to_bank_binding(self):
        p, q = bytes([1, 2]), bytes([3, 4])
        recording = register_recording(self.recordings, 'two banks', [('P', p), ('Q', q)])
        view = ViewLayout('PWORD', 'P', 0, 2, 1, 2, 'little')
        register_views(self.recordings, self.registry, recording, [view])
        self.assertEqual(register_recording(self.recordings, 'two banks', [('Q', q), ('P', p)]), recording)
        with self.assertRaisesRegex(ValueError, 'different banks'):
            register_recording(self.recordings, 'two banks', [('P', q), ('Q', p)])
        original = self.recordings.get(recording)
        self.assertEqual((read_bank(original.banks, 'P'), read_bank(original.banks, 'Q')), (p, q))
        self.assertEqual(source_check(self.recordings, self.registry, recording, 'PWORD').values, (513,))

    def test_invalid_recording_leaves_no_name(self):
        for banks in ({}, {'P': b''}, [('P', b'1'), ('P', b'2')]):
            with self.subTest(banks=banks), self.assertRaises(ValueError):
                register_recording(self.recordings, 'bad recording', banks)
        self.assertIsNone(self.recordings.find_by_name('bad recording'))
