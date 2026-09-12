"""Kill switch — a single in-memory boolean gate shared by the Risk Engine.

Design (from execution-model.md §10):
- State is in-process only.  A process restart resets to disarmed.
- Setting and clearing are both logged with a timestamp and a reason.
- Thread-safety is not a concern for this single-researcher tool, but the
  public API is intentionally synchronous so Phase 05 can call it directly.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from dataclasses import dataclass, field

_log = logging.getLogger(__name__)


@dataclass
class KillSwitchEvent:
    """Audit record for one arm/disarm event."""

    action: str  # "ARMED" | "DISARMED"
    reason: str
    occurred_at: datetime


class KillSwitch:
    """Single in-memory gate that blocks all new order approvals when armed.

    The switch is created disarmed.  Arm/disarm calls are idempotent — calling
    arm() when already armed just appends a new audit record.
    """

    def __init__(self) -> None:
        self._armed: bool = False
        self._log: list[KillSwitchEvent] = []

    # ------------------------------------------------------------------
    # State access
    # ------------------------------------------------------------------

    @property
    def is_armed(self) -> bool:
        """Return True when the kill switch is active."""
        return self._armed

    # ------------------------------------------------------------------
    # Operator actions
    # ------------------------------------------------------------------

    def arm(self, reason: str) -> None:
        """Arm the kill switch.  All subsequent evaluate() calls will fail rule 7.

        Args:
            reason: Human-readable explanation for the audit log.
        """
        self._armed = True
        event = KillSwitchEvent(
            action="ARMED",
            reason=reason,
            occurred_at=datetime.now(UTC),
        )
        self._log.append(event)
        _log.warning(
            "kill-switch ARMED at %s — reason: %s",
            event.occurred_at.isoformat(),
            reason,
        )

    def disarm(self, reason: str) -> None:
        """Disarm the kill switch.  Subsequent orders may be approved again.

        Args:
            reason: Human-readable explanation for the audit log.
        """
        self._armed = False
        event = KillSwitchEvent(
            action="DISARMED",
            reason=reason,
            occurred_at=datetime.now(UTC),
        )
        self._log.append(event)
        _log.warning(
            "kill-switch DISARMED at %s — reason: %s",
            event.occurred_at.isoformat(),
            reason,
        )

    # ------------------------------------------------------------------
    # Audit
    # ------------------------------------------------------------------

    @property
    def events(self) -> list[KillSwitchEvent]:
        """Return a read-only copy of the event log, oldest first."""
        return list(self._log)
