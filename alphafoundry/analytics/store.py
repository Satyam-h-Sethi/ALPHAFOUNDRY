"""DuckDB-backed persistence for analytics artifacts (FeatureVectors, Signals, Ranks, Regimes)."""

from __future__ import annotations

import json
from datetime import datetime
from uuid import UUID

import duckdb

from alphafoundry.analytics.config import AnalyticsConfig
from alphafoundry.analytics.features import FeatureRegistry
from alphafoundry.domain import (
    Direction,
    FeatureVector,
    InstrumentRank,
    RegimeState,
    Signal,
)

_CREATE_FEATURE_VECTORS = """
CREATE TABLE IF NOT EXISTS feature_vectors (
    feature_vector_id VARCHAR PRIMARY KEY,
    instrument_id     VARCHAR NOT NULL,
    as_of             TIMESTAMP NOT NULL,
    computed_at       TIMESTAMP NOT NULL,
    feature_version   VARCHAR(32) NOT NULL,
    features          VARCHAR NOT NULL
);
"""

_CREATE_SIGNALS = """
CREATE TABLE IF NOT EXISTS signals (
    signal_id         VARCHAR PRIMARY KEY,
    instrument_id     VARCHAR NOT NULL,
    as_of             TIMESTAMP NOT NULL,
    emitted_at        TIMESTAMP NOT NULL,
    direction         VARCHAR(16) NOT NULL,
    score             DOUBLE NOT NULL,
    confidence        DOUBLE NOT NULL,
    lineage           VARCHAR NOT NULL,
    signal_version    VARCHAR(32) NOT NULL,
    supersedes        VARCHAR
);
"""

_CREATE_INSTRUMENT_RANKS = """
CREATE TABLE IF NOT EXISTS instrument_ranks (
    rank_id           VARCHAR PRIMARY KEY,
    instrument_id     VARCHAR NOT NULL,
    universe_id       VARCHAR(64) NOT NULL,
    as_of             TIMESTAMP NOT NULL,
    rank              INTEGER NOT NULL,
    score             DOUBLE NOT NULL
);
"""

_CREATE_REGIME_STATES = """
CREATE TABLE IF NOT EXISTS regime_states (
    regime_id         VARCHAR PRIMARY KEY,
    instrument_id     VARCHAR NOT NULL,
    as_of             TIMESTAMP NOT NULL,
    regime            VARCHAR(32) NOT NULL,
    confidence        DOUBLE NOT NULL,
    metrics           VARCHAR NOT NULL,
    detector_version  VARCHAR(32) NOT NULL
);
"""


class AnalyticsStore:
    """DuckDB-backed storage for all Phase 03 analytics artefacts."""

    def __init__(
        self,
        cfg: AnalyticsConfig | None = None,
        registry: FeatureRegistry | None = None,
        conn: duckdb.DuckDBPyConnection | None = None,
    ) -> None:
        self._cfg = cfg or AnalyticsConfig()
        self._registry = registry or FeatureRegistry()
        self._conn = conn if conn is not None else duckdb.connect(self._cfg.db_path)
        self._conn.execute(_CREATE_FEATURE_VECTORS)
        self._conn.execute(_CREATE_SIGNALS)
        self._conn.execute(_CREATE_INSTRUMENT_RANKS)
        self._conn.execute(_CREATE_REGIME_STATES)

    @property
    def connection(self) -> duckdb.DuckDBPyConnection:
        return self._conn

    # ------------------------------------------------------------------
    # Writes
    # ------------------------------------------------------------------

    def insert_feature_vector(self, fv: FeatureVector) -> None:
        """Persist a FeatureVector after validating feature names against registry."""
        self._registry.validate_features(fv.features)
        self._conn.execute(
            """
            INSERT INTO feature_vectors
                (feature_vector_id, instrument_id, as_of, computed_at, feature_version, features)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                str(fv.feature_vector_id),
                str(fv.instrument_id),
                fv.as_of,
                fv.computed_at,
                fv.feature_version,
                json.dumps(fv.features),
            ],
        )

    def insert_signal(self, signal: Signal) -> None:
        """Persist an immutable Signal record."""
        lineage_json = json.dumps([item.model_dump() for item in signal.lineage])
        self._conn.execute(
            """
            INSERT INTO signals
                (signal_id, instrument_id, as_of, emitted_at, direction,
                 score, confidence, lineage, signal_version, supersedes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                str(signal.signal_id),
                str(signal.instrument_id),
                signal.as_of,
                signal.emitted_at,
                signal.direction.value,
                float(signal.score),
                float(signal.confidence),
                lineage_json,
                signal.signal_version,
                str(signal.supersedes) if signal.supersedes else None,
            ],
        )

    def insert_rank(self, rank: InstrumentRank) -> None:
        """Persist an InstrumentRank record."""
        self._conn.execute(
            """
            INSERT INTO instrument_ranks
                (rank_id, instrument_id, universe_id, as_of, rank, score)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                str(rank.rank_id),
                str(rank.instrument_id),
                rank.universe_id,
                rank.as_of,
                rank.rank,
                float(rank.score),
            ],
        )

    def insert_ranks(self, ranks: list[InstrumentRank]) -> None:
        """Batch persist multiple InstrumentRank records."""
        for r in ranks:
            self.insert_rank(r)

    def insert_regime_state(self, regime: RegimeState) -> None:
        """Persist a RegimeState record."""
        metrics_json = json.dumps(regime.metrics)
        self._conn.execute(
            """
            INSERT INTO regime_states
                (regime_id, instrument_id, as_of, regime, confidence, metrics, detector_version)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                str(regime.regime_id),
                str(regime.instrument_id),
                regime.as_of,
                regime.regime.value,
                float(regime.confidence),
                metrics_json,
                regime.detector_version,
            ],
        )

    # ------------------------------------------------------------------
    # Reads / Queries
    # ------------------------------------------------------------------

    def count_feature_vectors(self) -> int:
        return self._conn.execute("SELECT COUNT(*) FROM feature_vectors").fetchone()[0]  # type: ignore[index]

    def count_signals(self) -> int:
        return self._conn.execute("SELECT COUNT(*) FROM signals").fetchone()[0]  # type: ignore[index]

    def count_ranks(self) -> int:
        return self._conn.execute("SELECT COUNT(*) FROM instrument_ranks").fetchone()[0]  # type: ignore[index]

    def count_regime_states(self) -> int:
        return self._conn.execute("SELECT COUNT(*) FROM regime_states").fetchone()[0]  # type: ignore[index]

    def fetch_feature_vectors(
        self,
        instrument_id: UUID | None = None,
        limit: int = 1000,
    ) -> list[dict]:
        """Fetch feature vector rows, newest first."""
        if instrument_id is not None:
            rows = self._conn.execute(
                "SELECT * FROM feature_vectors WHERE instrument_id = ? ORDER BY as_of DESC LIMIT ?",
                [str(instrument_id), limit],
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM feature_vectors ORDER BY as_of DESC LIMIT ?",
                [limit],
            ).fetchall()
        cols = self._conn.description
        results = [dict(zip([c[0] for c in cols], row, strict=True)) for row in rows]
        for r in results:
            if isinstance(r.get("features"), str):
                r["features"] = json.loads(r["features"])
        return results

    def fetch_signals(
        self,
        instrument_id: UUID | None = None,
        direction: Direction | None = None,
        limit: int = 1000,
    ) -> list[dict]:
        """Fetch signal rows, newest first."""
        query = "SELECT * FROM signals"
        params: list = []
        conditions: list[str] = []

        if instrument_id is not None:
            conditions.append("instrument_id = ?")
            params.append(str(instrument_id))
        if direction is not None:
            conditions.append("direction = ?")
            params.append(direction.value)

        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        query += " ORDER BY as_of DESC LIMIT ?"
        params.append(limit)

        rows = self._conn.execute(query, params).fetchall()
        cols = self._conn.description
        results = [dict(zip([c[0] for c in cols], row, strict=True)) for row in rows]
        for r in results:
            if isinstance(r.get("lineage"), str):
                r["lineage"] = json.loads(r["lineage"])
        return results

    def fetch_ranks(
        self,
        universe_id: str | None = None,
        as_of: datetime | None = None,
        limit: int = 1000,
    ) -> list[dict]:
        """Fetch ranking rows, ordered by rank ascending."""
        query = "SELECT * FROM instrument_ranks"
        params: list = []
        conditions: list[str] = []

        if universe_id is not None:
            conditions.append("universe_id = ?")
            params.append(universe_id)
        if as_of is not None:
            conditions.append("as_of = ?")
            params.append(as_of)

        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        query += " ORDER BY rank ASC LIMIT ?"
        params.append(limit)

        rows = self._conn.execute(query, params).fetchall()
        cols = self._conn.description
        return [dict(zip([c[0] for c in cols], row, strict=True)) for row in rows]

    def fetch_regime_states(
        self,
        instrument_id: UUID | None = None,
        limit: int = 1000,
    ) -> list[dict]:
        """Fetch regime rows, newest first."""
        if instrument_id is not None:
            rows = self._conn.execute(
                "SELECT * FROM regime_states WHERE instrument_id = ? ORDER BY as_of DESC LIMIT ?",
                [str(instrument_id), limit],
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM regime_states ORDER BY as_of DESC LIMIT ?",
                [limit],
            ).fetchall()
        cols = self._conn.description
        results = [dict(zip([c[0] for c in cols], row, strict=True)) for row in rows]
        for r in results:
            if isinstance(r.get("metrics"), str):
                r["metrics"] = json.loads(r["metrics"])
        return results

    def close(self) -> None:
        """Close underlying DuckDB connection."""
        self._conn.close()
