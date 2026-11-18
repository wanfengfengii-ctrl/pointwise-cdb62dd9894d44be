import base64
from dataclasses import replace
from hashlib import sha256
import json

from audit.archive import read_audit, source_check
from audit.totals import ViewTotals
from handover.format import decode_package, encode_package
from offline.accept import accept_package
from tests import BenchCase


class HandoverTests(BenchCase):
    def test_selected_bytes_offline(self):
        recording = self.prepare()
        names = ('A', 'B', 'C')
        source_audits = tuple(source_check(self.recordings, self.registry, recording, name) for name in names)
        issued = self.publish(recording, names)
        selected = decode_package(issued.wire).payload.data
        self.assertEqual(sorted(selected), [1, 1, 2, 2, 3])
        self.assertNotIn(239, selected)
        self.assertNotIn(173, selected)
        self.disconnect_source()
        self.assertFalse(self.source_path.exists())
        parent = accept_package(self.offline, issued.wire)
        audit = read_audit(self.offline, parent)
        self.assertEqual(parent, issued.package_id)
        self.assertEqual(audit.views, source_audits)
        self.assertEqual(tuple(view.values for view in audit.views), ((513,), (515,), (513,)))

    def test_selected_reference_relations(self):
        recording = self.prepare()
        expected = {
            'A': ((('P', 0), ('P', 1)),),
            'B': ((('P', 1), ('P', 2)),),
            'C': ((('Q', 0), ('Q', 1)),),
            'R': ((('P', 1), ('P', 2)), (('P', 0), ('P', 1))),
            'O': ((('P', 0), ('P', 1)), (('P', 1), ('P', 2))),
            'M': ((('P', 1),),),
        }
        physical_bytes = {('P', 0): 1, ('P', 1): 2, ('P', 2): 3, ('Q', 0): 1, ('Q', 1): 2}
        issued = self.publish(recording, tuple(expected))
        payload = decode_package(issued.wire).payload
        by_source, by_ref = {}, {}
        self.assertEqual(tuple(view.name for view in payload.views), tuple(expected))
        for view in payload.views:
            for references, positions in zip(view.elements, expected[view.name], strict=True):
                for ref, position in zip(references, positions, strict=True):
                    self.assertEqual(by_source.setdefault(position, ref), ref)
                    self.assertEqual(by_ref.setdefault(ref, position), position)
                    self.assertEqual(payload.data[ref], physical_bytes[position])
        self.assertEqual(set(by_source), set(physical_bytes))
        self.assertEqual(set(by_ref), set(range(len(payload.data))))

    def test_selection_order(self):
        parent = self.handoff(('B', 'A', 'C'))
        audit = read_audit(self.offline, parent)
        self.assertEqual(
            [(view.name, view.values, view.totals) for view in audit.views],
            [('B', (515,), ViewTotals(1, 515, 515, 515)),
             ('A', (513,), ViewTotals(1, 513, 513, 513)),
             ('C', (513,), ViewTotals(1, 513, 513, 513))],
        )

    def test_invalid_selection_does_not_publish(self):
        recording = self.prepare()
        valid = self.publish(recording, ('A',))
        with self.assertRaises(KeyError):
            self.publish(recording, ('A', 'missing'))
        for invalid in ((), ('B', 'B')):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                self.publish(recording, invalid)
        rows = self.source_db.execute('SELECT package_id FROM issued_packages').fetchall()
        self.assertEqual(rows, [(valid.package_id,)])
        self.assertEqual(self.publish(recording, ('A',)), valid)

    def test_fixed_replay_across_reopen(self):
        recording = self.prepare()
        first = self.publish(recording, ('B', 'A', 'C'))
        self.source_db.close()
        self.open_source()
        first_again = self.publish(recording, ('B', 'A', 'C'))
        self.assertEqual(first_again, first)
        self.assertNotEqual(self.publish(recording, ('A', 'B', 'C')).package_id, first.package_id)
        self.disconnect_source()
        self.assertEqual(accept_package(self.offline, first.wire), first.package_id)
        audit = read_audit(self.offline, first.package_id)
        self.reopen_offline()
        self.assertEqual(accept_package(self.offline, first_again.wire), first.package_id)
        self.assertEqual(read_audit(self.offline, first.package_id), audit)
        self.assertEqual(self.inventory(), (((first.package_id, None),), ()))

    def test_corrupt_package(self):
        issued = self.publish(self.prepare(), ('A', 'B', 'C'))
        corrupted = json.loads(issued.wire)
        data = bytearray(base64.b64decode(corrupted['body']['data']))
        data[0] ^= 1
        corrupted['body']['data'] = base64.b64encode(data).decode('ascii')
        self.disconnect_source()
        with self.assertRaisesRegex(ValueError, 'checksum'):
            accept_package(self.offline, json.dumps(corrupted).encode('ascii'))
        self.assertEqual(self.inventory(), ((), ()))
        with self.assertRaises(KeyError):
            read_audit(self.offline, issued.package_id)
        self.assertEqual(accept_package(self.offline, issued.wire), issued.package_id)
        self.assertEqual(read_audit(self.offline, issued.package_id).views[0].values, (513,))

    def test_checksum_does_not_excuse_invalid_references(self):
        issued = self.publish(self.prepare(), ('A', 'B', 'C'))
        for bad_refs in ([0, 99], [0, 0], [0], [True, 1]):
            with self.subTest(refs=bad_refs):
                outer = json.loads(issued.wire)
                outer['body']['views'][0]['elements'][0] = bad_refs
                signed = {key: outer[key] for key in ('version', 'body')}
                canonical = json.dumps(signed, sort_keys=True, separators=(',', ':')).encode('ascii')
                outer['sha256'] = sha256(canonical).hexdigest()
                with self.assertRaises(ValueError):
                    accept_package(self.offline, json.dumps(outer).encode('ascii'))
        self.assertEqual(self.inventory(), ((), ()))

    def test_same_id_different_valid_content_rejected(self):
        issued = self.publish(self.prepare(), ('A', 'B', 'C'))
        envelope = decode_package(issued.wire)
        changed_data = bytes([99]) + envelope.payload.data[1:]
        changed = replace(envelope, payload=replace(envelope.payload, data=changed_data))
        wire = encode_package(changed)
        self.assertEqual(decode_package(wire).package_id, issued.package_id)
        self.disconnect_source()
        parent = accept_package(self.offline, issued.wire)
        with self.assertRaisesRegex(ValueError, 'different content'):
            accept_package(self.offline, wire)
        self.reopen_offline()
        self.assertEqual(self.offline.get(parent).package, envelope)
        self.assertEqual(tuple(view.values[0] for view in read_audit(self.offline, parent).views), (513, 515, 513))
        self.assertEqual(self.inventory(), (((parent, None),), ()))
