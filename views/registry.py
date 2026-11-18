from collections.abc import Iterable
from sqlite3 import Connection

from capture.banks import bank_lengths
from capture.catalog import RecordingCatalog
from views.layout import ViewLayout
from views.validation import validate_view_batch


class ViewRegistry:
    def __init__(self, connection: Connection):
        self._db = connection

    def initialize(self) -> None:
        self._db.execute('PRAGMA foreign_keys = ON')
        self._db.execute('''
            CREATE TABLE IF NOT EXISTS view_layouts (
                recording_id TEXT NOT NULL,
                name TEXT NOT NULL,
                bank_name TEXT NOT NULL,
                start_byte INTEGER NOT NULL,
                stride_hex TEXT NOT NULL,
                element_count INTEGER NOT NULL,
                width INTEGER NOT NULL,
                byteorder TEXT NOT NULL,
                bit_start INTEGER,
                bit_length INTEGER,
                PRIMARY KEY (recording_id, name),
                FOREIGN KEY (recording_id, bank_name)
                    REFERENCES recording_banks(recording_id, bank_name)
            )
        ''')
        # Older SQLite databases predate the optional bit-window columns.
        columns = {row[1] for row in self._db.execute('PRAGMA table_info(view_layouts)')}
        for column in ('bit_start', 'bit_length'):
            if column not in columns:
                self._db.execute(f'ALTER TABLE view_layouts ADD COLUMN {column} INTEGER')

    def get_catalog(self, recording_id: str) -> tuple[ViewLayout, ...]:
        rows = self._db.execute('''
            SELECT name, bank_name, start_byte, stride_hex, element_count, width,
                   byteorder, bit_start, bit_length
            FROM view_layouts WHERE recording_id = ? ORDER BY name
        ''', (recording_id,))
        return tuple(
            ViewLayout(name, bank, start, int(stride, 16), count, width, byteorder,
                       bit_start, bit_length)
            for name, bank, start, stride, count, width, byteorder, bit_start, bit_length in rows
        )

    def store_batch(
        self, recording_id: str, layouts: tuple[ViewLayout, ...],
    ) -> tuple[ViewLayout, ...]:
        with self._db:
            self._db.execute('BEGIN IMMEDIATE')
            known = {layout.name: layout for layout in self.get_catalog(recording_id)}
            pending = []
            for layout in layouts:
                existing = known.get(layout.name)
                if existing is None:
                    pending.append(layout)
                elif layout != existing:
                    raise ValueError(f'view {layout.name!r} already has a different fixed definition')
            self._db.executemany('''
                INSERT INTO view_layouts (
                    recording_id, name, bank_name, start_byte, stride_hex,
                    element_count, width, byteorder, bit_start, bit_length
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                (recording_id, view.name, view.bank_name, view.start, hex(view.stride),
                 view.count, view.width, view.byteorder, view.bit_start, view.bit_length)
                for view in pending
            ))
            return self.get_catalog(recording_id)


def register_views(
    recordings: RecordingCatalog,
    registry: ViewRegistry,
    recording_id: str,
    layouts: Iterable[ViewLayout],
) -> tuple[ViewLayout, ...]:
    recording = recordings.get(recording_id)
    batch = validate_view_batch(layouts, bank_lengths(recording.banks))
    return registry.store_batch(recording_id, batch)
