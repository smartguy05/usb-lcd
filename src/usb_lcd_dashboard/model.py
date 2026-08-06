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
    activity: str = ""
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


Key = tuple[str, str]


class StateStore:
    def __init__(
        self,
        active_ttl: int = 180,
        approval_ttl: int = 90,
        tool_ttl: int = 900,
        switch_dwell: float = 4.0,
    ):
        self.sessions: dict[Key, SessionState] = {}
        self.active_ttl = active_ttl
        self.approval_ttl = approval_ttl
        self.tool_ttl = tool_ttl
        self.switch_dwell = switch_dwell
        # What each session looked like the last time it was on screen, so a
        # session is only given a turn when it has something new to show.
        self.shown: dict[Key, datetime] = {}
        self.showing: Key | None = None
        self.showing_since: datetime | None = None

    def apply(self, update: SessionState) -> SessionState:
        key = (update.provider, update.session_id)
        previous = self.sessions.get(key)
        if previous:
            if update.extra.get("event") == "StatusLine":
                update.phase = previous.phase
                update.detail = previous.detail
                update.activity = previous.activity
                update.ended = previous.ended
            values = {
                name: getattr(update, name)
                for name in update.__dataclass_fields__
                if name not in {"extra", "started_at"}
            }
            # "activity" is absent on purpose: a prompt or stop event carries no
            # tool, and its empty activity must clear the stale one.
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

    def _ttl(self, state: SessionState) -> float:
        """A session waiting on a tool has work in flight and emits nothing
        until the tool returns, which can take far longer than the idle TTL."""
        return self.tool_ttl if state.phase == "TOOL" else self.active_ttl

    def active(self, now: datetime | None = None) -> SessionState | None:
        """Pick the session to display.

        The screen holds one session, so it has to be shared. A session takes
        the screen when it has an update that has not been shown yet, and keeps
        it for switch_dwell seconds; without that floor a session emitting an
        event every second would take every frame and quieter sessions would
        never be readable. A pending approval preempts immediately.
        """
        now = now or utc_now()
        live = {
            key: state
            for key, state in self.sessions.items()
            if not state.ended
            and (now - state.updated_at).total_seconds() <= self._ttl(state)
        }
        for stale in set(self.shown) - set(live):
            del self.shown[stale]
        if not live:
            self.showing = None
            self.showing_since = None
            return None

        approvals = [
            (key, state)
            for key, state in live.items()
            if state.phase == "APPROVAL"
            and (now - state.updated_at).total_seconds() <= self.approval_ttl
        ]
        if approvals:
            choice = max(approvals, key=lambda item: item[1].updated_at)
        else:
            held = self.showing if self.showing in live else None
            elapsed = (
                (now - self.showing_since).total_seconds()
                if held and self.showing_since
                else None
            )
            if held and elapsed is not None and elapsed < self.switch_dwell:
                choice = (held, live[held])
            else:
                waiting = [
                    (key, state)
                    for key, state in live.items()
                    if key != held and state.updated_at != self.shown.get(key)
                ]
                if waiting:
                    choice = max(waiting, key=lambda item: item[1].updated_at)
                elif held:
                    choice = (held, live[held])
                else:
                    choice = max(live.items(), key=lambda item: item[1].updated_at)

        key, state = choice
        if key != self.showing:
            self.showing = key
            self.showing_since = now
        self.shown[key] = state.updated_at
        return state

