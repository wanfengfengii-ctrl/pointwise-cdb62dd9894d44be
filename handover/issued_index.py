from dataclasses import dataclass
import json
from sqlite3 import Connection

from handover.selection import ResolvedSelection


@dataclass(frozen=True)
class IssuedPackage:
    package_id: str
    wire: bytes


class IssuedIndex:
    def __init__(self, connection: Connection):
        self._db = connection

    def initialize(self) -> None:
        self._db.execute('PRAGMA foreign_keys = ON')
        self._db.execute('''
            CREATE TABLE IF NOT EXISTS issued_packages (
                recording_id TEXT NOT NULL REFERENCES recordings(recording_id),
                selection_key TEXT NOT NULL,
                package_id TEXT NOT NULL UNIQUE,
                wire BLOB NOT NULL,
                PRIMARY KEY (recording_id, selection_key)
            )
        ''')

    @staticmethod
    def _key(selection: ResolvedSelection) -> tuple[str, str]:
        return selection.recording_id, json.dumps(selection.names, separators=(',', ':'))

    def find_selection(self, selection: ResolvedSelection) -> IssuedPackage | None:
        row = self._db.execute('''
            SELECT package_id, wire FROM issued_packages
            WHERE recording_id = ? AND selection_key = ?
        ''', self._key(selection)).fetchone()
        return IssuedPackage(*row) if row is not None else None

    def store(self, selection: ResolvedSelection, issued: IssuedPackage) -> IssuedPackage:
        with self._db:
            self._db.execute('BEGIN IMMEDIATE')
            previous = self.find_selection(selection)
            if previous is not None:
                return previous
            self._db.execute('''
                INSERT INTO issued_packages (recording_id, selection_key, package_id, wire)
                VALUES (?, ?, ?, ?)
            ''', (*self._key(selection), issued.package_id, issued.wire))
        return issued
