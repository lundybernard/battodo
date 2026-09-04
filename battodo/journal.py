"""Append-only JSONL event journal, one per source directory.

Envelope follows OpenFrameKeeper's event store (its ADR 0002) so the two
projects share a vocabulary. `prev_hash`/`hash` are reserved and null in
v1, and the commit-boundary fields are omitted. A command can append
several events -- a completion cascade, or a parent stamp beside the
child that names it -- and nothing marks them as one commit, so a
partial write is not detectable. Both are additive to add later, needing
no schema_version bump.

While markdown remains authoritative the journal is a *partial* record:
hand-edits bypass btodo and so bypass this log. Every payload therefore
carries a full task snapshot, which is what lets a future authority flip
replay state without having observed each change.
"""

from datetime import datetime, timezone
from fcntl import LOCK_EX, LOCK_UN, flock
from json import dumps, loads
from os import fsync
from pathlib import Path
from secrets import choice
from typing import Any
from uuid import uuid4

SCHEMA_VERSION = 1
JOURNAL_DIRNAME = '.journal'
JOURNAL_FILENAME = 'log.jsonl'
ID_ALPHABET = '0123456789abcdefghijklmnopqrstuvwxyz'
ID_LENGTH = 6


def new_task_id() -> str:
    """A short base36 identifier for lazy `[ID:...]` injection."""
    return ''.join(choice(ID_ALPHABET) for _ in range(ID_LENGTH))


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Journal:
    """The event log for one source directory."""

    def __init__(self, source_dir: Path) -> None:
        self.path = Path(source_dir) / JOURNAL_DIRNAME / JOURNAL_FILENAME

    def read(self) -> list[dict[str, Any]]:
        """Every event in order. Missing journal reads as empty."""
        if not self.path.exists():
            return []
        return [
            loads(line)
            for line in self.path.read_text().splitlines()
            if line.strip()
        ]

    def append(
        self,
        event_type: str,
        stream_id: str,
        payload: dict[str, Any],
        *,
        actor: str,
        source_file: str,
        occurred_at: str | None = None,
    ) -> dict[str, Any]:
        """Append one event and return it.

        Holds an advisory exclusive `flock` for the read-then-append, so
        `seq` and `stream_seq` cannot race a second writer, and fsyncs
        before releasing.
        """
        self.path.parent.mkdir(parents=True, exist_ok=True)
        recorded_at = _utc_now()

        with self.path.open('a+', encoding='utf-8') as handle:
            flock(handle.fileno(), LOCK_EX)
            try:
                handle.seek(0)
                existing = [
                    loads(line)
                    for line in handle.read().splitlines()
                    if line.strip()
                ]
                event = {
                    'seq': len(existing) + 1,
                    'event_id': str(uuid4()),
                    'stream_id': stream_id,
                    'stream_seq': sum(
                        e['stream_id'] == stream_id for e in existing
                    )
                    + 1,
                    'type': event_type,
                    'schema_version': SCHEMA_VERSION,
                    'occurred_at': occurred_at or recorded_at,
                    'recorded_at': recorded_at,
                    'prev_hash': None,
                    'hash': None,
                    'metadata': {
                        'actor': actor,
                        'source_file': source_file,
                    },
                    'payload': payload,
                }
                handle.write(dumps(event) + '\n')
                handle.flush()
                fsync(handle.fileno())
            finally:
                flock(handle.fileno(), LOCK_UN)

        return event
