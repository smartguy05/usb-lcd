import json
from datetime import datetime, timezone

from usb_lcd_dashboard.teams import TeamsIntegration, parse_chats, plain_text


def chat(*, created, read, sender="other", body="Hello", topic="Project"):
    return {
        "topic": topic,
        "viewpoint": {"lastMessageReadDateTime": read},
        "lastMessagePreview": {
            "createdDateTime": created,
            "from": {"user": {"id": sender, "displayName": "Alex"}},
            "body": {"content": body},
        },
        "members": [
            {"userId": "me", "displayName": "Me"},
            {"userId": "other", "displayName": "Alex"},
        ],
    }


def test_chat_html_becomes_safe_compact_text():
    assert plain_text("<p>Hello &amp; <b>welcome</b></p><div>Next</div>") == "Hello & welcome Next"


def test_only_newer_incoming_chat_previews_are_unread():
    result = parse_chats(
        [
            chat(created="2026-08-17T12:03:00Z", read="2026-08-17T12:00:00Z"),
            chat(created="2026-08-17T11:00:00Z", read="2026-08-17T12:00:00Z"),
            chat(created="2026-08-17T13:00:00Z", read=None, sender="me"),
        ],
        "me",
    )
    assert result.unread_conversations == 1
    assert result.latest.sender == "Alex"
    assert result.latest.preview == "Hello"


def test_a_direct_chat_uses_the_other_members_name():
    result = parse_chats(
        [chat(created="2026-08-17T12:03:00Z", read=None, topic=None)], "me"
    )
    assert result.latest.conversation == "Alex"


class FakeApp:
    def __init__(self):
        self.accounts = [{"username": "alex@example.com"}]
        self.removed = []

    def get_accounts(self):
        return self.accounts

    def acquire_token_silent(self, scopes, account):
        return {"access_token": "secret-token"}

    def remove_account(self, account):
        self.removed.append(account)
        self.accounts.remove(account)


class DeviceApp(FakeApp):
    def __init__(self):
        super().__init__()
        self.accounts = []

    def initiate_device_flow(self, scopes):
        return {
            "user_code": "ABCD-EFGH",
            "verification_uri": "https://microsoft.com/devicelogin",
            "expires_in": 900,
        }

    def acquire_token_by_device_flow(self, flow):
        self.accounts = [{"username": "alex@example.com"}]
        return {
            "access_token": "secret-token",
            "id_token_claims": {"preferred_username": "alex@example.com"},
        }


class Response:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return json.dumps(self.payload).encode()


def test_polling_follows_graph_pagination_without_leaking_the_token():
    calls = []
    pages = [
        {"id": "me"},
        {"value": [], "@odata.nextLink": "https://graph.microsoft.com/v1.0/next"},
        {
            "value": [chat(created="2026-08-17T12:03:00Z", read=None)],
        },
    ]

    def open_(request, timeout):
        calls.append((request.full_url, request.headers, timeout))
        return Response(pages.pop(0))

    integration = TeamsIntegration(
        environ={"USB_LCD_TEAMS_CLIENT_ID": "client", "USB_LCD_TEAMS_TENANT_ID": "tenant"},
        app_factory=FakeApp,
        urlopen=open_,
    )
    result = integration.poll_once()
    assert result.unread_conversations == 1
    assert result.account == "alex@example.com"
    assert len(calls) == 3
    assert all(call[1]["Authorization"] == "Bearer secret-token" for call in calls)


def test_missing_environment_identity_is_reported_without_auth_imports():
    integration = TeamsIntegration(environ={})
    assert integration.status()["status"] == "unconfigured"
    assert integration.status()["configured"] is False


def test_device_login_publishes_only_the_code_then_the_account():
    integration = TeamsIntegration(
        environ={"USB_LCD_TEAMS_CLIENT_ID": "client", "USB_LCD_TEAMS_TENANT_ID": "tenant"},
        app_factory=DeviceApp,
    )
    pending = integration.connect()
    assert pending["user_code"] == "ABCD-EFGH"
    integration._auth_thread.join(timeout=2)
    status = integration.status()
    assert status["status"] == "connected"
    assert status["account"] == "alex@example.com"
    assert "token" not in json.dumps(status).lower()


def test_disconnect_clears_the_account_and_snapshot():
    app = FakeApp()
    integration = TeamsIntegration(
        environ={"USB_LCD_TEAMS_CLIENT_ID": "client", "USB_LCD_TEAMS_TENANT_ID": "tenant"},
        app_factory=lambda: app,
    )
    integration._last_good = parse_chats(
        [chat(created="2026-08-17T12:03:00Z", read=None)], "me"
    )
    integration.disconnect()
    assert app.removed
    assert integration.snapshot().status == "disconnected"
    assert integration.snapshot().latest is None


def test_a_refresh_error_keeps_the_last_good_snapshot_but_marks_it_stale():
    integration = TeamsIntegration(environ={})
    good = parse_chats([chat(created="2026-08-17T12:03:00Z", read=None)], "me")
    integration._last_good = good
    integration._failure(OSError("offline"))
    assert integration.snapshot().latest == good.latest
    assert integration.snapshot().stale is True
    assert integration.snapshot().error == "offline"
