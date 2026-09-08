"""Tests for the Deduplicator."""

from __future__ import annotations

from alphafoundry.pipeline.deduplicator import Deduplicator


class TestDeduplicator:
    def test_first_key_not_duplicate(self):
        d = Deduplicator()
        assert not d.is_duplicate("venue:instr:1")

    def test_second_occurrence_is_duplicate(self):
        d = Deduplicator()
        d.is_duplicate("venue:instr:1")
        assert d.is_duplicate("venue:instr:1")

    def test_different_keys_not_duplicate(self):
        d = Deduplicator()
        d.is_duplicate("venue:instr:1")
        assert not d.is_duplicate("venue:instr:2")

    def test_seen_count_increments(self):
        d = Deduplicator()
        d.is_duplicate("a")
        d.is_duplicate("b")
        d.is_duplicate("a")  # duplicate — should not increment
        assert d.seen_count == 2

    def test_reset_clears_seen_set(self):
        d = Deduplicator()
        d.is_duplicate("venue:instr:1")
        d.reset()
        assert d.seen_count == 0
        assert not d.is_duplicate("venue:instr:1")  # no longer seen

    def test_many_keys_independent(self):
        d = Deduplicator()
        keys = [f"venue:instr:{i}" for i in range(100)]
        for k in keys:
            assert not d.is_duplicate(k)
        for k in keys:
            assert d.is_duplicate(k)
        assert d.seen_count == 100
