"""Tests for Session domain model."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from alphafoundry.domain import Session
from alphafoundry.domain.enums import SessionStatus, SessionType


def _utc(year, month, day, hour, minute) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=UTC)


class TestSession:
    def _session(self, **kwargs) -> Session:
        defaults = {
            "venue_id": "NSE_EQ",
            "session_type": SessionType.NORMAL,
            "open_time": _utc(2024, 1, 2, 3, 45),  # 09:15 IST = 03:45 UTC
            "close_time": _utc(2024, 1, 2, 10, 0),  # 15:30 IST = 10:00 UTC
        }
        defaults.update(kwargs)
        return Session(**defaults)

    def test_valid_session(self):
        s = self._session()
        assert s.status == SessionStatus.SCHEDULED

    def test_close_before_open_is_invalid(self):
        with pytest.raises(ValidationError):
            self._session(
                open_time=_utc(2024, 1, 2, 10, 0),
                close_time=_utc(2024, 1, 2, 3, 45),
            )

    def test_equal_times_is_invalid(self):
        t = _utc(2024, 1, 2, 3, 45)
        with pytest.raises(ValidationError):
            self._session(open_time=t, close_time=t)

    def test_naive_open_time_is_invalid(self):
        with pytest.raises(ValidationError):
            self._session(open_time=datetime(2024, 1, 2, 3, 45))

    def test_naive_close_time_is_invalid(self):
        with pytest.raises(ValidationError):
            self._session(close_time=datetime(2024, 1, 2, 10, 0))

    def test_session_is_immutable(self):
        s = self._session()
        with pytest.raises(ValidationError):
            s.status = SessionStatus.OPEN  # type: ignore[misc]
