import json
from datetime import timezone

import pytest

from usb_lcd_dashboard.discord import DiscordIntegration, TokenStore, parse_message


class Response:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def read(self):
        return json.dumps(self.payload).encode()


def test_message_parser_uses_discord_names_and_attachment_fallback():
    item = parse_message(
        {"timestamp": "2026-08-17T12:00:00Z", "author": {"username": "alex"},
         "member": {"nick": "Alex"}, "content": "", "attachments": [{"filename": "design.png"}]},
        "Studio · #general",
    )
    assert item.provider == "discord"
    assert item.sender == "Alex"
    assert item.preview == "Shared design.png"
    assert item.created_at.tzinfo == timezone.utc


def test_token_store_round_trips_and_clears(tmp_path):
    store = TokenStore(tmp_path / "token")
    store.save("secret")
    assert store.load() == "secret"
    store.clear()
    assert store.load() == ""


def test_save_token_rejects_a_normal_user_token(tmp_path):
    integration = DiscordIntegration(
        token_store=TokenStore(tmp_path / "token"), state_path=tmp_path / "state.json",
        urlopen=lambda *_args, **_kwargs: Response({"id": "1", "username": "person", "bot": False}),
    )
    with pytest.raises(ValueError, match="not a bot token"):
        integration.save_token("user-token")


def test_discovery_and_polling_count_only_human_messages(tmp_path):
    calls = []

    def open_url(request, **_kwargs):
        path = request.full_url.split("/api/v10", 1)[1]
        calls.append(path)
        if path == "/users/@me": return Response({"id": "9", "username": "lcd", "bot": True})
        if path == "/users/@me/guilds": return Response([{"id": "1", "name": "Studio"}])
        if path == "/guilds/1/channels": return Response([{"id": "2", "name": "general", "type": 0}])
        if path.startswith("/channels/2/messages"):
            return Response([
                {"id": "11", "timestamp": "2026-08-17T12:00:00Z", "content": "hello", "author": {"username": "Alex", "bot": False}},
                {"id": "12", "timestamp": "2026-08-17T12:01:00Z", "content": "automated", "author": {"username": "Bot", "bot": True}},
            ])
        raise AssertionError(path)

    integration = DiscordIntegration(token_store=TokenStore(tmp_path / "token"),
        state_path=tmp_path / "state.json", urlopen=open_url)
    status = integration.save_token("bot-token")
    assert status["channels"][0]["name"] == "general"
    integration.configure(("2",))
    assert integration.poll_once().unread_conversations == 0  # initial baseline
    integration._state["2"]["cursor"] = "10"
    snapshot = integration.poll_once()
    assert snapshot.unread_conversations == 1
    assert snapshot.latest.preview == "hello"
    assert "token" not in json.dumps(integration.status()).lower()
    integration.clear()
    assert integration.snapshot().unread_conversations == 0
