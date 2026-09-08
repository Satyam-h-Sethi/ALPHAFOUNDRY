"""Data pipeline — Phase 02.

Public API::

    from alphafoundry.pipeline import DataPipeline, PipelineConfig

End-to-end flow::

    Adapter → Normaliser → Validator → Deduplicator
           → Staleness → Store writer → Audit log
"""

from alphafoundry.pipeline.audit import AuditLog, IngestOutcome
from alphafoundry.pipeline.config import PipelineConfig
from alphafoundry.pipeline.deduplicator import Deduplicator
from alphafoundry.pipeline.normaliser import Normaliser
from alphafoundry.pipeline.pipeline import DataPipeline
from alphafoundry.pipeline.staleness import StalenessDetector
from alphafoundry.pipeline.store import MarketDataStore
from alphafoundry.pipeline.validator import ValidationResult, Validator

__all__ = [
    "DataPipeline",
    "PipelineConfig",
    "Normaliser",
    "Validator",
    "ValidationResult",
    "Deduplicator",
    "StalenessDetector",
    "MarketDataStore",
    "AuditLog",
    "IngestOutcome",
]
