"""Provider-neutral message state handed from integrations to widgets."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class MessageItem:
    provider: str
    conversation: str
    sender: str
    preview: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class MessageSnapshot:
    """One immutable read of an integration's current state."""

    status: str = "disconnected"
    latest: MessageItem | None = None
    unread_conversations: int = 0
    updated_at: datetime | None = None
    account: str = ""
    error: str = ""
    stale: bool = False

