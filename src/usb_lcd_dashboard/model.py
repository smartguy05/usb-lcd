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
        # One entry per tile that can hold a session, and when each was filled.
        # The 3.5" panel is simply the one-slot case.
        self.slots: list[Key | None] = []
        self.since: list[datetime | None] = []

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

    def _resize(self, slots: int) -> None:
        while len(self.slots) < slots:
            self.slots.append(None)
            self.since.append(None)
        del self.slots[slots:]
        del self.since[slots:]

    def _elapsed(self, index: int, now: datetime) -> float:
        since = self.since[index]
        return float("inf") if since is None else (now - since).total_seconds()

    def active(self, now: datetime | None = None) -> SessionState | None:
        """The session on a single-tile panel — the one-slot case of assign()."""
        return self.assign(1, now)[0]

    def assign(
        self, slots: int, now: datetime | None = None
    ) -> list[SessionState | None]:
        """Place live sessions into `slots` tiles, newest-interesting first.

        The tiles are the cap: with at most `slots` live sessions every one gets
        a stable tile and nothing ever moves. Beyond that the surplus take turns,
        under the same rules a single tile has always used — a session only takes
        a turn when it has something new to show, it holds its tile for
        switch_dwell seconds so it stays readable, and a pending approval jumps
        the queue immediately.

        A placed session is never relocated, only evicted, so nothing hops from
        tile to tile between frames.
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
        self._resize(slots)
        if not live or slots <= 0:
            self.slots = [None] * slots
            self.since = [None] * slots
            return [None] * slots

        def approval(key: Key) -> bool:
            state = live.get(key)
            return (
                state is not None
                and state.phase == "APPROVAL"
                and (now - state.updated_at).total_seconds() <= self.approval_ttl
            )

        def newest_first(keys) -> list[Key]:
            return sorted(keys, key=lambda key: live[key].updated_at, reverse=True)

        # Drop sessions that have expired, and any duplicate of one already held
        # at a lower index, so a session can never occupy two tiles.
        seen: set[Key] = set()
        for index, key in enumerate(self.slots):
            if key is None:
                continue
            if key not in live or key in seen:
                self.slots[index] = None
                self.since[index] = None
            else:
                seen.add(key)

        approvals = newest_first([key for key in live if approval(key)])
        fresh = newest_first(
            [
                key
                for key in live
                if key not in seen and live[key].updated_at != self.shown.get(key)
            ]
        )
        # Tiles filled during this call are off limits below: without this a
        # dwell of zero would let each candidate evict the previous one and the
        # least interesting session would end up on screen.
        placed: set[int] = set()

        def place(index: int, key: Key) -> None:
            self.slots[index] = key
            self.since[index] = now
            placed.add(index)

        def on_screen() -> set[Key]:
            return {key for key in self.slots if key is not None}

        # An empty tile displaces nothing, so it fills without waiting on dwell.
        # The third group keeps a tile from sitting blank while a session that
        # simply has no news is available to show.
        queue = [key for key in approvals if key not in seen]
        queue += [key for key in fresh if key not in queue]
        queue += [
            key for key in newest_first(live) if key not in seen and key not in queue
        ]
        for index in range(slots):
            if self.slots[index] is None and queue:
                place(index, queue.pop(0))

        # An approval ignores the dwell floor. It evicts the tile that has been
        # sitting longest rather than always tile zero, so it displaces the least
        # recently interesting session instead of one that just arrived.
        for key in approvals:
            if key in on_screen():
                continue
            victims = [
                index
                for index in range(slots)
                if self.slots[index] is not None
                and index not in placed
                and not approval(self.slots[index])
            ]
            if victims:
                index = max(victims, key=lambda i: (self._elapsed(i, now), i))
            else:
                occupied = [
                    index
                    for index in range(slots)
                    if self.slots[index] is not None and index not in placed
                ]
                if not occupied:
                    break
                index = min(occupied, key=lambda i: live[self.slots[i]].updated_at)
            place(index, key)

        # Everything else waits for a tile to have been readable long enough.
        for key in fresh:
            if key in on_screen():
                continue
            eligible = [
                index
                for index in range(slots)
                if self.slots[index] is not None
                and index not in placed
                and not approval(self.slots[index])
                and self._elapsed(index, now) >= self.switch_dwell
            ]
            if not eligible:
                break
            place(max(eligible, key=lambda i: (self._elapsed(i, now), i)), key)

        for key in self.slots:
            if key is not None:
                self.shown[key] = live[key].updated_at
        return [live[key] if key is not None else None for key in self.slots]

