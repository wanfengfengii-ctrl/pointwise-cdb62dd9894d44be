from collections.abc import Callable
from dataclasses import dataclass
from sqlite3 import Connection

from handover.format import PackageEnvelope, decode_package, encode_package


@dataclass(frozen=True)
class RevisionSnapshot:
    package: PackageEnvelope
    parent_id: str | None = None

    @property
    def package_id(self) -> str:
        return self.package.package_id


@dataclass(frozen=True)
class StoredReceipt:
    child_id: str
    parent_id: str
    request_count: int


class RevisionStore:
    def __init__(self, connection: Connection):
        self._db = connection

    def initialize(self) -> None:
        self._db.execute('PRAGMA foreign_keys = ON')
        with self._db:
            self._db.execute('BEGIN IMMEDIATE')
            self._db.execute('''
                CREATE TABLE IF NOT EXISTS revisions (
                    package_id TEXT PRIMARY KEY,
                    parent_id TEXT REFERENCES revisions(package_id),
                    wire BLOB NOT NULL
                )
            ''')
            self._db.execute('''
                CREATE TABLE IF NOT EXISTS correction_receipts (
                    child_id TEXT PRIMARY KEY REFERENCES revisions(package_id),
                    parent_id TEXT NOT NULL REFERENCES revisions(package_id),
                    request_count INTEGER NOT NULL CHECK (request_count > 0)
                )
            ''')

    def get(self, package_id: str) -> RevisionSnapshot:
        row = self._db.execute('''
            SELECT parent_id, wire FROM revisions WHERE package_id = ?
        ''', (package_id,)).fetchone()
        if row is None:
            raise KeyError(package_id)
        parent_id, wire = row
        return RevisionSnapshot(decode_package(wire), parent_id)

    def get_receipt(self, child_id: str) -> StoredReceipt:
        row = self._db.execute('''
            SELECT child_id, parent_id, request_count FROM correction_receipts WHERE child_id = ?
        ''', (child_id,)).fetchone()
        if row is None:
            raise KeyError(child_id)
        return StoredReceipt(*row)

    def store_import(self, package: PackageEnvelope, wire: bytes) -> str:
        """Persist the validated envelope and its original encoded bytes."""
        with self._db:
            self._db.execute('BEGIN IMMEDIATE')
            try:
                previous = self.get(package.package_id)
            except KeyError:
                self._db.execute('''
                    INSERT INTO revisions (package_id, parent_id, wire) VALUES (?, NULL, ?)
                ''', (package.package_id, wire))
            else:
                if previous.parent_id is not None or previous.package != package:
                    raise ValueError(f'package ID already binds different content: {package.package_id!r}')
        return package.package_id

    def commit_correction(
        self,
        child: RevisionSnapshot,
        receipt: StoredReceipt,
        *,
        before_commit: Callable[[], None] | None = None,
    ) -> None:
        if child.parent_id is None or (receipt.child_id, receipt.parent_id) != (
            child.package_id, child.parent_id,
        ):
            raise ValueError('receipt must describe the child and its direct parent')
        wire = encode_package(child.package)
        with self._db:
            self._db.execute('BEGIN IMMEDIATE')
            self._db.execute('''
                INSERT INTO revisions (package_id, parent_id, wire) VALUES (?, ?, ?)
            ''', (child.package_id, child.parent_id, wire))
            self._db.execute('''
                INSERT INTO correction_receipts (child_id, parent_id, request_count) VALUES (?, ?, ?)
            ''', (receipt.child_id, receipt.parent_id, receipt.request_count))
            if before_commit is not None:
                before_commit()
