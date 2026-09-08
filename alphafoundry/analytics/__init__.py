"""Analytics Layer — Feature Engine, Signal Engine, Regime Detector, Ranking Engine, Persistence, Replay."""

from alphafoundry.analytics.config import AnalyticsConfig
from alphafoundry.analytics.feature_engine import FeatureEngine
from alphafoundry.analytics.features import (
    FeatureDefinition,
    FeatureRegistry,
    compute_bid_ask_spread,
    compute_market_depth_liquidity,
    compute_momentum,
    compute_realised_volatility,
    compute_returns,
    compute_volume_ratio,
)
from alphafoundry.analytics.ranking import RankingEngine
from alphafoundry.analytics.regime import RegimeDetector
from alphafoundry.analytics.replay import HistoricalReplayEngine, ReplayStepResult
from alphafoundry.analytics.signals import SignalEngine
from alphafoundry.analytics.store import AnalyticsStore

__all__ = [
    "AnalyticsConfig",
    "AnalyticsStore",
    "FeatureDefinition",
    "FeatureEngine",
    "FeatureRegistry",
    "HistoricalReplayEngine",
    "RankingEngine",
    "RegimeDetector",
    "ReplayStepResult",
    "SignalEngine",
    "compute_bid_ask_spread",
    "compute_market_depth_liquidity",
    "compute_momentum",
    "compute_realised_volatility",
    "compute_returns",
    "compute_volume_ratio",
]
