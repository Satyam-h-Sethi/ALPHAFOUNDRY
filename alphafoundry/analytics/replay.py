"""Historical Replay / Backtest Engine — zero lookahead time-series analytics runner."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from alphafoundry.analytics.feature_engine import FeatureEngine
from alphafoundry.analytics.ranking import RankingEngine
from alphafoundry.analytics.regime import RegimeDetector
from alphafoundry.analytics.signals import SignalEngine
from alphafoundry.analytics.store import AnalyticsStore
from alphafoundry.domain import (
    FeatureVector,
    InstrumentRank,
    OHLCBar,
    Quote,
    RegimeState,
    Signal,
)


class ReplayStepResult(BaseModel):
    """Container for analytics computed at a single historical point in time."""

    model_config = ConfigDict(frozen=True)

    as_of: datetime
    feature_vectors: dict[UUID, FeatureVector] = Field(default_factory=dict)
    signals: dict[UUID, Signal] = Field(default_factory=dict)
    regimes: dict[UUID, RegimeState] = Field(default_factory=dict)
    ranks: list[InstrumentRank] = Field(default_factory=list)


class HistoricalReplayEngine:
    """Simulates point-in-time execution of the analytics pipeline over historical windows.

    At each timestamp step t:
      1. Slices historical bars and quotes with timestamp <= t (zero lookahead).
      2. Computes FeatureVectors for all active instruments.
      3. Generates directional Signals with lineage.
      4. Classifies market RegimeState.
      5. Computes cross-sectional InstrumentRanks within the universe.
      6. Optionally persists all artifacts to AnalyticsStore.
    """

    def __init__(
        self,
        feature_engine: FeatureEngine | None = None,
        signal_engine: SignalEngine | None = None,
        regime_detector: RegimeDetector | None = None,
        ranking_engine: RankingEngine | None = None,
        store: AnalyticsStore | None = None,
    ) -> None:
        self._feature_engine = feature_engine or FeatureEngine()
        self._signal_engine = signal_engine or SignalEngine()
        self._regime_detector = regime_detector or RegimeDetector()
        self._ranking_engine = ranking_engine or RankingEngine()
        self._store = store

    def run(
        self,
        bars_by_instrument: dict[UUID, Sequence[OHLCBar]],
        universe_id: str = "DEFAULT",
        quotes_by_instrument: dict[UUID, Sequence[Quote]] | None = None,
        timestamps: Sequence[datetime] | None = None,
        persist: bool = False,
    ) -> list[ReplayStepResult]:
        """Execute point-in-time replay across chronological timestamps.

        Parameters
        ----------
        bars_by_instrument : dict[UUID, Sequence[OHLCBar]]
            Historical bars keyed by instrument UUID.
        universe_id : str
            Universe ID for cross-sectional ranking.
        quotes_by_instrument : dict[UUID, Sequence[Quote]] | None
            Optional historical quotes keyed by instrument UUID.
        timestamps : Sequence[datetime] | None
            Specific evaluation timestamps. If None, derived from all bar close times.
        persist : bool
            If True and store is configured, persists step artifacts to DuckDB store.

        Returns
        -------
        list[ReplayStepResult]
            Chronological analytics trace records.
        """
        # Determine evaluation timeline
        if timestamps is None:
            all_ts: set[datetime] = set()
            for bars in bars_by_instrument.values():
                for b in bars:
                    ts = b.bar_close if b.bar_close.tzinfo else b.bar_close.replace(tzinfo=UTC)
                    all_ts.add(ts)
            eval_timestamps = sorted(all_ts)
        else:
            eval_timestamps = sorted(
                [ts if ts.tzinfo else ts.replace(tzinfo=UTC) for ts in timestamps]
            )

        quotes_map = quotes_by_instrument or {}
        results: list[ReplayStepResult] = []

        for as_of in eval_timestamps:
            step_fvs: dict[UUID, FeatureVector] = {}
            step_signals: dict[UUID, Signal] = {}
            step_regimes: dict[UUID, RegimeState] = {}

            for inst_id, bars in bars_by_instrument.items():
                # Find latest quote <= as_of if available
                inst_quotes = quotes_map.get(inst_id, [])
                valid_quotes = [
                    q for q in inst_quotes
                    if (q.timestamp if q.timestamp.tzinfo else q.timestamp.replace(tzinfo=UTC)) <= as_of
                ]
                latest_quote = max(valid_quotes, key=lambda q: q.timestamp) if valid_quotes else None

                # 1. Feature Engine
                fv = self._feature_engine.compute_features(
                    instrument_id=inst_id,
                    as_of=as_of,
                    bars=bars,
                    quote=latest_quote,
                )
                step_fvs[inst_id] = fv

                # 2. Signal Engine
                sig = self._signal_engine.generate_signal(feature_vector=fv)
                step_signals[inst_id] = sig

                # 3. Regime Detector
                reg = self._regime_detector.detect_regime(
                    instrument_id=inst_id,
                    as_of=as_of,
                    bars=bars,
                )
                step_regimes[inst_id] = reg

                if persist and self._store is not None:
                    self._store.insert_feature_vector(fv)
                    self._store.insert_signal(sig)
                    self._store.insert_regime_state(reg)

            # 4. Cross-sectional Ranking
            ranks = self._ranking_engine.rank_universe(
                signals=list(step_signals.values()),
                universe_id=universe_id,
                as_of=as_of,
                instrument_filter=set(bars_by_instrument.keys()),
            )

            if persist and self._store is not None:
                self._store.insert_ranks(ranks)

            step_res = ReplayStepResult(
                as_of=as_of,
                feature_vectors=step_fvs,
                signals=step_signals,
                regimes=step_regimes,
                ranks=ranks,
            )
            results.append(step_res)

        return results
