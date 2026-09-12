"""Unit tests for KillSwitch."""

from __future__ import annotations

from alphafoundry.risk import KillSwitch


def test_kill_switch_starts_disarmed() -> None:
    ks = KillSwitch()
    assert not ks.is_armed
    assert ks.events == []


def test_arm_sets_flag_and_logs_event() -> None:
    ks = KillSwitch()
    ks.arm("operator halt")
    assert ks.is_armed
    assert len(ks.events) == 1
    assert ks.events[0].action == "ARMED"
    assert ks.events[0].reason == "operator halt"


def test_disarm_clears_flag_and_logs_event() -> None:
    ks = KillSwitch()
    ks.arm("bad signal")
    ks.disarm("issue resolved")
    assert not ks.is_armed
    assert len(ks.events) == 2
    assert ks.events[1].action == "DISARMED"
    assert ks.events[1].reason == "issue resolved"


def test_arm_twice_appends_two_events() -> None:
    ks = KillSwitch()
    ks.arm("first reason")
    ks.arm("second reason")
    assert ks.is_armed
    assert len(ks.events) == 2
    assert ks.events[0].reason == "first reason"
    assert ks.events[1].reason == "second reason"


def test_events_returns_copy() -> None:
    ks = KillSwitch()
    ks.arm("test")
    events_a = ks.events
    events_b = ks.events
    assert events_a is not events_b  # new list each time
    assert events_a == events_b


def test_disarm_without_arm_is_allowed() -> None:
    """Disarming an already-disarmed switch is a no-op (idempotent)."""
    ks = KillSwitch()
    ks.disarm("preventive clear")
    assert not ks.is_armed
    assert len(ks.events) == 1
