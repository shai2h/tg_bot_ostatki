from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class BotHealthState:
    runtime_running: bool = False
    mode: str = "unknown"
    last_incoming_event_at: datetime | None = None
    last_successful_send_at: datetime | None = None
    last_error: str | None = None
    handlers_registered: bool = False

    def mark_runtime_started(self, mode: str, *, handlers_registered: bool) -> None:
        self.runtime_running = True
        self.mode = mode
        self.handlers_registered = handlers_registered
        self.last_error = None

    def mark_runtime_stopped(self) -> None:
        self.runtime_running = False

    def record_incoming(self) -> None:
        self.last_incoming_event_at = _utc_now()

    def record_successful_send(self) -> None:
        self.last_successful_send_at = _utc_now()
        self.last_error = None
        from app.observability.prometheus_metrics import record_bot_answer

        record_bot_answer()

    def record_error(self, error: BaseException | str) -> None:
        self.last_error = str(error)

    def snapshot(self) -> dict[str, object]:
        return {
            "runtime_running": self.runtime_running,
            "mode": self.mode,
            "handlers_registered": self.handlers_registered,
            "last_incoming_event_at": (
                self.last_incoming_event_at.isoformat() if self.last_incoming_event_at else None
            ),
            "last_successful_send_at": (
                self.last_successful_send_at.isoformat() if self.last_successful_send_at else None
            ),
            "last_error": self.last_error,
        }


bot_health = BotHealthState()
