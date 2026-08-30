"""
F134 — Demo Sandbox Provisioning
Clock abstraction: SystemClock (production) + FrozenClock (test helper).

Usage:
    from app.lib.time import SystemClock, FrozenClock
    clock = SystemClock()
    clock.utcnow()  # -> datetime (UTC, aware)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timezone


class Clock(ABC):
    """Abstract clock interface used for dependency injection in services."""

    @abstractmethod
    def utcnow(self) -> datetime:
        """Return the current time as a timezone-aware UTC datetime."""


class SystemClock(Clock):
    """Production clock backed by the real wall clock."""

    def utcnow(self) -> datetime:
        return datetime.now(tz=timezone.utc)


class FrozenClock(Clock):
    """Test helper clock that always returns a fixed instant."""

    def __init__(self, frozen_at: datetime | None = None) -> None:
        if frozen_at is None:
            frozen_at = datetime(2026, 4, 25, 12, 0, 0, tzinfo=timezone.utc)
        self._frozen_at = frozen_at

    def utcnow(self) -> datetime:
        return self._frozen_at

    def advance(self, **kwargs: float) -> None:
        """Advance the frozen time by the given timedelta kwargs (e.g. days=1)."""
        from datetime import timedelta

        self._frozen_at += timedelta(**kwargs)
