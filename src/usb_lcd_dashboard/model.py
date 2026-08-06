from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(slots=True)
class SessionState:
    provider: str
    session_id: str
    updated_at: datetime
    started_at: datetime
    phase: str = "READY"
    detail: str = ""
    model: str = ""
    cwd: str = ""
    permission_mode: str = ""
    context_percent: float | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    cost_usd: float | None = None
    ended: bool = False
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def project(self) -> str:
        return Path(self.cwd).name if self.cwd else "unknown project"


class StateStore:
    def __init__(self, active_ttl: int = 180, approval_ttl: int = 90):
        self.sessions: dict[tuple[str, str], SessionState] = {}
        self.active_ttl = active_ttl
        self.approval_ttl = approval_ttl

    def apply(self, update: SessionState) -> SessionState:
        key = (update.provider, update.session_id)
        previous = self.sessions.get(key)
        if previous:
            if update.extra.get("event") == "StatusLine":
                update.phase = previous.phase
                update.detail = previous.detail
                update.ended = previous.ended
            values = {
                name: getattr(update, name)
                for name in update.__dataclass_fields__
                if name not in {"extra", "started_at"}
            }
            for optional in (
                "detail",
                "model",
                "cwd",
                "permission_mode",
                "context_percent",
                "input_tokens",
                "output_tokens",
                "cost_usd",
            ):
                if values[optional] in ("", None):
                    values[optional] = getattr(previous, optional)
            update = replace(
                previous,
                **values,
                extra={**previous.extra, **update.extra},
            )
        self.sessions[key] = update
        return update

    def active(self, now: datetime | None = None) -> SessionState | None:
        now = now or utc_now()
        candidates = [
            state
            for state in self.sessions.values()
            if not state.ended
            and (now - state.updated_at).total_seconds() <= self.active_ttl
        ]
        approvals = [
            state
            for state in candidates
            if state.phase == "APPROVAL"
            and (now - state.updated_at).total_seconds() <= self.approval_ttl
        ]
        pool = approvals or candidates
        return max(pool, key=lambda state: state.updated_at) if pool else None

