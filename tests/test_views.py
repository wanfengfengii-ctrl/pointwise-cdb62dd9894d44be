from audit.archive import source_check
from capture.recording import register_recording
from tests import BenchCase
from views.layout import ViewLayout
from views.registry import register_views


class ViewTests(BenchCase):
    def _original(self):
        recording = register_recording(self.recordings, 'bounds', {'P': bytes([1, 2, 3, 4])})
        original = ViewLayout('GOOD', 'P', 3, -1, 2, 1, 'little')
        register_views(self.recordings, self.registry, recording, [original])
        return recording, original

    def test_reverse_view_bounds(self):
        recording, original = self._original()
        invalid = ViewLayout('BAD', 'P', 1, -2, 2, 2, 'big')
        with self.assertRaisesRegex(ValueError, 'outside'):
            register_views(self.recordings, self.registry, recording, [invalid])
        self.assertEqual(self.registry.get_catalog(recording), (original,))
        self.assertEqual(source_check(self.recordings, self.registry, recording, 'GOOD').values, (4, 3))

    def test_reverse_bounds_reject_entire_batch(self):
        recording, original = self._original()
        valid = ViewLayout('VALID_NEW', 'P', 0, 2, 2, 2, 'little')
        invalid = ViewLayout('BAD_NEW', 'P', 1, -2, 2, 2, 'big')
        with self.assertRaisesRegex(ValueError, 'outside'):
            register_views(self.recordings, self.registry, recording, [valid, invalid])
        self.assertEqual(self.registry.get_catalog(recording), (original,))
        for name in ('VALID_NEW', 'BAD_NEW'):
            with self.subTest(name=name), self.assertRaises(KeyError):
                source_check(self.recordings, self.registry, recording, name)
        self.assertEqual(source_check(self.recordings, self.registry, recording, 'GOOD').values, (4, 3))

    def test_fixed_definition_replay_and_conflict(self):
        recording, original = self._original()
        new = ViewLayout('EXTRA', 'P', 0, 1, 2, 1, 'little')
        conflict = ViewLayout('GOOD', 'P', 0, 1, 2, 1, 'little')
        with self.assertRaisesRegex(ValueError, 'different fixed definition'):
            register_views(self.recordings, self.registry, recording, [new, conflict])
        self.assertEqual(self.registry.get_catalog(recording), (original,))
        self.assertEqual(register_views(self.recordings, self.registry, recording, [original]), (original,))

    def test_single_element_can_have_large_signed_stride(self):
        recording, _ = self._original()
        layout = ViewLayout('SINGLE', 'P', 1, -(1 << 80), 1, 2, 'big')
        result = register_views(self.recordings, self.registry, recording, [layout])
        self.assertIn(layout, result)
        self.assertEqual(source_check(self.recordings, self.registry, recording, 'SINGLE').values, (515,))
