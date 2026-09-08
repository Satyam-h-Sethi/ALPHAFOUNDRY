"""Deduplicator — idempotency gate for the ingest pipeline.

Per data-model.md §5 the idempotency key is ``venue_id + ":" + sequence_id``.
The first event with a given key is accepted; subsequent arrivals with the
same key are rejected as duplicates and must not enter primary storage.

The in-process implementation uses an in-memory set.  This is intentional
for Phase 02: the SyntheticAdapter runs within a single process and the
set fits comfortably in memory for typical session volumes.  A Bloom-filter
or persistent dedup table can replace this in a later phase without changing
the public interface.
"""

from __future__ import annotations


class Deduplicator:
    """In-memory idempotency gate.

    Thread-safety note: not thread-safe.  The pipeline is designed for
    single-threaded async processing; no locking is needed.
    """

    def __init__(self) -> None:
        self._seen: set[str] = set()

    def is_duplicate(self, idempotency_key: str) -> bool:
        """Return True if *idempotency_key* has been seen before.

        If not seen, records the key and returns False.
        """
        if idempotency_key in self._seen:
            return True
        self._seen.add(idempotency_key)
        return False

    def reset(self) -> None:
        """Clear all seen keys — intended for testing only."""
        self._seen.clear()

    @property
    def seen_count(self) -> int:
        """Number of unique keys accepted so far."""
        return len(self._seen)
