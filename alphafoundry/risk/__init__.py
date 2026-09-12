"""Risk Engine — Phase 04.

Pre-trade risk gate implementing all seven rules from execution-model.md §9.

Public API::

    from alphafoundry.risk import KillSwitch, RiskContext, RiskEngine
    from alphafoundry.domain import RiskConfig, RiskDecision, RuleViolation, PositionLimit

    engine = RiskEngine(config=RiskConfig(...), kill_switch=KillSwitch())
    decision = engine.evaluate(order, RiskContext(...))
"""

from alphafoundry.risk.config import default_risk_config
from alphafoundry.risk.engine import RiskContext, RiskEngine
from alphafoundry.risk.kill_switch import KillSwitch, KillSwitchEvent

# Re-export domain types for convenience — callers need not import from two places.
from alphafoundry.domain.risk import PositionLimit, RiskConfig, RiskDecision, RuleViolation

__all__ = [
    # Engine
    "RiskEngine",
    "RiskContext",
    # Kill switch
    "KillSwitch",
    "KillSwitchEvent",
    # Config helpers
    "default_risk_config",
    # Domain types (re-exported for convenience)
    "PositionLimit",
    "RiskConfig",
    "RiskDecision",
    "RuleViolation",
]
