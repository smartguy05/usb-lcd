"""Filtered Windows notification state for the notifications widget.

The public model and filtering code are platform-neutral so Linux builds and the
test suite never import WinRT.  The adapter imports the projections only inside
its worker thread on Windows.
"""

from __future__ import annotations

import asyncio
import logging
import os
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterable

LOG = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class NotificationItem:
    id: int
    app_id: str
    app_name: str
    title: str
    body: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class NotificationApp:
    id: str
    name: str


@dataclass(frozen=True, slots=True)
class NotificationSnapshot:
    status: str = "unsupported"
    items: tuple[NotificationItem, ...] = ()
    apps: tuple[NotificationApp, ...] = ()
    updated_at: datetime | None = None
    changed_at: datetime | None = None
    error: str = ""


def filter_items(
    items: Iterable[NotificationItem],
    app_ids: Iterable[str],
    include_terms: Iterable[str] = (),
    exclude_terms: Iterable[str] = (),
) -> tuple[NotificationItem, ...]:
    """Return newest-first items accepted by the configured literal filters."""
    allowed = {value.casefold() for value in app_ids if value}
    includes = tuple(value.casefold() for value in include_terms if value.strip())
    excludes = tuple(value.casefold() for value in exclude_terms if value.strip())
    accepted = []
    seen: set[tuple[str, int]] = set()
    for item in items:
        key = (item.app_id.casefold(), item.id)
        if key in seen or item.app_id.casefold() not in allowed:
            continue
        seen.add(key)
        haystack = "\n".join((item.app_name, item.title, item.body)).casefold()
        if any(term in haystack for term in excludes):
            continue
        if includes and not any(term in haystack for term in includes):
            continue
        accepted.append(item)
    return tuple(sorted(accepted, key=lambda item: item.created_at, reverse=True))


def _clean_values(values: Iterable[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(value.strip() for value in values if value.strip()))


class WindowsNotificationIntegration:
    """Own the WinRT listener on one background asyncio thread."""

    def __init__(self) -> None:
        status = "permission_required" if os.name == "nt" else "unsupported"
        self._snapshot = NotificationSnapshot(status=status)
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._request_access = threading.Event()
        self._wake = threading.Event()
        self._thread: threading.Thread | None = None
        self._app_ids: tuple[str, ...] = ()
        self._include_terms: tuple[str, ...] = ()
        self._exclude_terms: tuple[str, ...] = ()

    def configure(
        self,
        enabled: bool,
        app_ids: Iterable[str],
        include_terms: Iterable[str] = (),
        exclude_terms: Iterable[str] = (),
    ) -> None:
        with self._lock:
            self._app_ids = _clean_values(app_ids) if enabled else ()
            self._include_terms = _clean_values(include_terms)
            self._exclude_terms = _clean_values(exclude_terms)
        self._wake.set()

    def start(self) -> None:
        if os.name != "nt" or self._thread is not None:
            return
        self._thread = threading.Thread(
            target=self._run, name="usb-lcd-windows-notifications", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()
        if self._thread is not None:
            self._thread.join(timeout=3)
            self._thread = None

    def request_access(self) -> dict:
        if os.name != "nt":
            return self.status()
        self._request_access.set()
        self._wake.set()
        return self.status()

    def snapshot(self) -> NotificationSnapshot:
        with self._lock:
            return self._snapshot

    def status(self) -> dict:
        snap = self.snapshot()
        return {
            "status": snap.status,
            "error": snap.error,
            "updated_at": snap.updated_at.isoformat() if snap.updated_at else None,
            "apps": [{"id": app.id, "name": app.name} for app in snap.apps],
            "matching": len(snap.items),
        }

    def _publish(
        self,
        status: str,
        *,
        all_items: Iterable[NotificationItem] = (),
        error: str = "",
    ) -> None:
        now = datetime.now(timezone.utc)
        raw = tuple(all_items)
        apps = tuple(
            NotificationApp(app_id, name)
            for app_id, name in sorted(
                {item.app_id: item.app_name for item in raw}.items(),
                key=lambda pair: pair[1].casefold(),
            )
        )
        with self._lock:
            filtered = filter_items(
                raw, self._app_ids, self._include_terms, self._exclude_terms
            )
            old = self._snapshot
            changed = old.changed_at
            identity = tuple((item.app_id, item.id) for item in filtered)
            if identity != tuple((item.app_id, item.id) for item in old.items):
                changed = now
            self._snapshot = NotificationSnapshot(
                status=status,
                items=filtered,
                apps=apps,
                updated_at=now,
                changed_at=changed or now,
                error=error,
            )

    def _run(self) -> None:
        apartment_ready = False
        try:
            from winrt.runtime import ApartmentType, init_apartment

            init_apartment(ApartmentType.SINGLE_THREADED)
            apartment_ready = True
            asyncio.run(self._async_run())
        except Exception as exc:  # pragma: no cover - Windows/runtime boundary
            LOG.exception("Windows notification listener stopped")
            self._publish("error", error=str(exc))
        finally:
            if apartment_ready:
                from winrt.runtime import uninit_apartment

                uninit_apartment()

    async def _async_run(self) -> None:  # pragma: no cover - exercised on Windows
        from winrt.windows.ui.notifications import (
            KnownNotificationBindings,
            NotificationKinds,
        )
        from winrt.windows.ui.notifications.management import (
            UserNotificationListener,
            UserNotificationListenerAccessStatus,
        )

        listener = UserNotificationListener.current
        dirty = True

        def changed(_sender, _args):
            nonlocal dirty
            dirty = True
            self._wake.set()

        changed_token = None
        try:
            while not self._stop.is_set():
                if self._request_access.is_set():
                    self._request_access.clear()
                    status = await listener.request_access_async()
                    dirty = True
                else:
                    status = listener.get_access_status()
                if status == UserNotificationListenerAccessStatus.DENIED:
                    self._publish("denied")
                elif status != UserNotificationListenerAccessStatus.ALLOWED:
                    self._publish("permission_required")
                elif dirty:
                    if changed_token is None:
                        changed_token = listener.add_notification_changed(changed)
                    raw = await listener.get_notifications_async(NotificationKinds.TOAST)
                    parsed = []
                    for notification in raw:
                        try:
                            binding = notification.notification.visual.get_binding(
                                KnownNotificationBindings.toast_generic
                            )
                            texts = [] if binding is None else [
                                element.text for element in binding.get_text_elements()
                                if element.text
                            ]
                            if not texts:
                                continue
                            created = notification.creation_time
                            if created.tzinfo is None:
                                created = created.replace(tzinfo=timezone.utc)
                            parsed.append(NotificationItem(
                                id=int(notification.id),
                                app_id=notification.app_info.app_user_model_id,
                                app_name=notification.app_info.display_info.display_name,
                                title=texts[0],
                                body="\n".join(texts[1:]),
                                created_at=created,
                            ))
                        except Exception:
                            LOG.exception("Ignoring an unreadable Windows notification")
                    self._publish("connected", all_items=parsed)
                    dirty = False
                self._wake.clear()
                await asyncio.to_thread(self._wake.wait, 2.0)
                # Reconcile periodically as well as on the change event.
                dirty = True
        finally:
            if changed_token is not None:
                listener.remove_notification_changed(changed_token)
