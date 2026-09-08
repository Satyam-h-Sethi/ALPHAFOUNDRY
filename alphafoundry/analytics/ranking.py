"""Ranking Engine — cross-sectional ranking of instruments within configured universes."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID

from alphafoundry.domain import InstrumentRank, Signal


class RankingEngine:
    """Computes cross-sectional ranks for instruments in a universe."""

    def rank_universe(
        self,
        signals: Sequence[Signal],
        universe_id: str,
        as_of: datetime,
        instrument_filter: Sequence[UUID] | set[UUID] | None = None,
        by_conviction: bool = False,
    ) -> list[InstrumentRank]:
        """Rank instruments by signal score or conviction. Rank 1 is top/highest.

        Parameters
        ----------
        signals : Sequence[Signal]
            Active signals to rank.
        universe_id : str
            Identifier of the universe (e.g. 'NIFTY50_TOP10').
        as_of : datetime
            Point-in-time reference timestamp.
        instrument_filter : Sequence[UUID] | set[UUID] | None
            Optional universe membership filter.
        by_conviction : bool
            If True, ranks by absolute conviction (|score| * confidence) descending.
            If False (default), ranks by directional score descending.

        Returns
        -------
        list[InstrumentRank]
            Sorted ranking records (Rank 1 first).
        """
        as_of_utc = as_of if as_of.tzinfo is not None else as_of.replace(tzinfo=UTC)
        filter_set = set(instrument_filter) if instrument_filter is not None else None

        # 1. Filter signals matching as_of and universe membership
        matched: dict[UUID, Signal] = {}
        for s in signals:
            s_ts = s.as_of if s.as_of.tzinfo is not None else s.as_of.replace(tzinfo=UTC)
            if (
                s_ts <= as_of_utc
                and (filter_set is None or s.instrument_id in filter_set)
                and (s.instrument_id not in matched or s.as_of > matched[s.instrument_id].as_of)
            ):
                matched[s.instrument_id] = s

        if not matched:
            return []

        # 2. Sort deterministically
        def sort_key(s: Signal) -> tuple:
            if by_conviction:
                conviction = abs(s.score) * s.confidence
                return (-conviction, -s.score, str(s.instrument_id))
            return (-s.score, -s.confidence, str(s.instrument_id))

        sorted_signals = sorted(matched.values(), key=sort_key)

        # 3. Assign 1-based ranks
        ranks: list[InstrumentRank] = []
        for rank_idx, s in enumerate(sorted_signals, start=1):
            ranks.append(
                InstrumentRank(
                    instrument_id=s.instrument_id,
                    universe_id=universe_id,
                    as_of=as_of_utc,
                    rank=rank_idx,
                    score=s.score,
                )
            )

        return ranks
