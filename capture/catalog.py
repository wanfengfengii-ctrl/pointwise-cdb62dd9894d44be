from dataclasses import dataclass
from sqlite3 import Connection
from uuid import uuid4

from capture.banks import RecordingBank


@dataclass(frozen=True)
class StoredRecording:
    recording_id: str
    external_name: str
    fingerprint: str
    banks: tuple[RecordingBank, ...]


class RecordingCatalog:
    def __init__(self, connection: Connection):
        self._db = connection

    def initialize(self) -> None:
        self._db.execute('PRAGMA foreign_keys = ON')
        with self._db:
            self._db.execute('BEGIN IMMEDIATE')
            self._db.execute('''
                CREATE TABLE IF NOT EXISTS recordings (
                    recording_id TEXT PRIMARY KEY,
                    external_name TEXT NOT NULL UNIQUE,
                    fingerprint TEXT NOT NULL
                )
            ''')
            self._db.execute('''
                CREATE TABLE IF NOT EXISTS recording_banks (
                    recording_id TEXT NOT NULL REFERENCES recordings(recording_id),
                    bank_name TEXT NOT NULL,
                    data BLOB NOT NULL CHECK (length(data) > 0),
                    PRIMARY KEY (recording_id, bank_name)
                )
            ''')

    def _load(self, row) -> StoredRecording:
        recording_id, name, fingerprint = row
        banks = self._db.execute('''
            SELECT bank_name, data FROM recording_banks
            WHERE recording_id = ? ORDER BY bank_name
        ''', (recording_id,))
        return StoredRecording(
            recording_id, name, fingerprint,
            tuple(RecordingBank(bank_name, data) for bank_name, data in banks),
        )

    def find_by_name(self, external_name: str) -> StoredRecording | None:
        row = self._db.execute('''
            SELECT recording_id, external_name, fingerprint FROM recordings
            WHERE external_name = ?
        ''', (external_name,)).fetchone()
        return self._load(row) if row is not None else None

    def get(self, recording_id: str) -> StoredRecording:
        row = self._db.execute('''
            SELECT recording_id, external_name, fingerprint FROM recordings
            WHERE recording_id = ?
        ''', (recording_id,)).fetchone()
        if row is None:
            raise KeyError(recording_id)
        return self._load(row)

    def store(
        self, external_name: str, banks: tuple[RecordingBank, ...], fingerprint: str,
    ) -> StoredRecording:
        with self._db:
            self._db.execute('BEGIN IMMEDIATE')
            existing = self.find_by_name(external_name)
            if existing is not None:
                return existing
            recording_id = 'rec-' + uuid4().hex
            self._db.execute('''
                INSERT INTO recordings (recording_id, external_name, fingerprint)
                VALUES (?, ?, ?)
            ''', (recording_id, external_name, fingerprint))
            self._db.executemany('''
                INSERT INTO recording_banks (recording_id, bank_name, data) VALUES (?, ?, ?)
            ''', ((recording_id, bank.name, bank.data) for bank in banks))
        return StoredRecording(recording_id, external_name, fingerprint, banks)
