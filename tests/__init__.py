import sqlite3
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from capture.catalog import RecordingCatalog
from demo import load_sample, prepare_sample
from handover.issue import issue_package
from handover.issued_index import IssuedIndex
from offline.accept import accept_package
from offline.revisions import RevisionStore
from views.registry import ViewRegistry


class BenchCase(unittest.TestCase):
    def setUp(self):
        scratch = TemporaryDirectory(prefix='bench-test-')
        self.addCleanup(scratch.cleanup)
        self.root = Path(scratch.name)
        self.source_path = self.root / 'source.sqlite'
        self.offline_path = self.root / 'offline.sqlite'
        self.open_source()
        self.open_offline()

    def open_source(self):
        self.source_db = sqlite3.connect(self.source_path)
        self.addCleanup(self.source_db.close)
        self.recordings = RecordingCatalog(self.source_db)
        self.registry = ViewRegistry(self.source_db)
        self.index = IssuedIndex(self.source_db)
        self.recordings.initialize()
        self.registry.initialize()
        self.index.initialize()

    def open_offline(self):
        self.offline_db = sqlite3.connect(self.offline_path)
        self.addCleanup(self.offline_db.close)
        self.offline = RevisionStore(self.offline_db)
        self.offline.initialize()

    def reopen_offline(self):
        self.offline_db.close()
        self.open_offline()

    def prepare(self):
        return prepare_sample(self.recordings, self.registry, load_sample())

    def publish(self, recording, names):
        return issue_package(self.recordings, self.registry, self.index, recording, names)

    def disconnect_source(self):
        self.source_db.close()
        self.source_path.rename(self.root / 'disconnected.sqlite')

    def handoff(self, names=('A', 'B', 'C')):
        issued = self.publish(self.prepare(), names)
        self.disconnect_source()
        return accept_package(self.offline, issued.wire)

    def inventory(self):
        revisions = self.offline_db.execute('SELECT package_id, parent_id FROM revisions ORDER BY package_id')
        receipts = self.offline_db.execute('''
            SELECT child_id, parent_id, request_count FROM correction_receipts ORDER BY child_id
        ''')
        return tuple(revisions), tuple(receipts)
