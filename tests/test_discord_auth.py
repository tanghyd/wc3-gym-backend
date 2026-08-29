"""The Discord login: state, membership, roles and /me.

Discord itself is stood in for: the code exchange, the identify call and
the bot calls in app/services/discord.py are patched per test.
"""

import urllib.parse
from typing import Any

import pytest
from httpx2 import Client

from app.core.security import decode_token
from app.services import discord

ACCOUNT = {"id": "42", "username": "player", "global_name": "Player", "avatar": "abc"}

# A guild whose owner is someone else and whose one role carries no permissions.
GUILD = {"owner_id": "999", "roles": [{"id": "plain", "permissions": "0"}]}


class FakeResponse:
    def __init__(self, status_code: int, body: dict[str, Any]) -> None:
        self.status_code = status_code
        self.ok = status_code < 400
        self.body = body

    def json(self) -> dict[str, Any]:
        return self.body


def stub_discord(
    monkeypatch: pytest.MonkeyPatch,
    member_status: int = 200,
    member_roles: list[str] | None = None,
    guild: dict[str, Any] | None = None,
    account: dict[str, Any] | None = None,
) -> None:
    def bot_get(path: str) -> FakeResponse:
        if "/members/" in path:
            return FakeResponse(member_status, {"roles": member_roles or []})
        return FakeResponse(200, guild or GUILD)

    monkeypatch.setenv("DISCORD_GUILD_ID", "316390574808760322")
    monkeypatch.setenv("ADMIN_DISCORD_IDS", "220202568490418179")
    monkeypatch.setenv("FRONTEND_URL", "http://localhost:5003")
    monkeypatch.setattr(discord, "exchange_code", lambda code: "discord-token")
    monkeypatch.setattr(discord, "identify", lambda token: account or ACCOUNT)
    monkeypatch.setattr(discord, "_bot_get", bot_get)


def start_state(client: Client) -> str:
    """The state the start route signed."""
    resp = client.get("/auth/discord/start")
    assert resp.status_code == 302
    query = urllib.parse.urlparse(resp.headers["location"]).query
    return urllib.parse.parse_qs(query)["state"][0]


def log_in(client: Client) -> dict[str, str]:
    """The tokens the callback hands to the frontend."""
    resp = client.get(
        "/auth/discord/callback",
        params={"code": "the-code", "state": start_state(client)},
    )
    assert resp.status_code == 302, resp.json()
    fragment = urllib.parse.urlparse(resp.headers["location"]).fragment
    return {
        key: value[0]
        for key, value in urllib.parse.parse_qs(fragment.split("?", 1)[1]).items()
    }


def headers(tokens: dict[str, str]) -> dict[str, str]:
    return {"Authorization": f"Bearer {tokens['access_token']}"}


def test_start_redirects_to_discord_with_a_signed_state(client: Client) -> None:
    resp = client.get("/auth/discord/start")
    assert resp.status_code == 302
    location = resp.headers["location"]
    assert location.startswith("https://discord.com/api/v10/oauth2/authorize?")
    assert "scope=identify" in location
    claims = decode_token(urllib.parse.parse_qs(location.split("?")[1])["state"][0])
    assert claims["type"] == "state"


def test_a_state_token_is_no_access_token(client: Client) -> None:
    state = start_state(client)
    resp = client.get("/me", headers={"Authorization": f"Bearer {state}"})
    assert resp.status_code == 422


def test_callback_with_a_forged_state(
    client: Client, monkeypatch: pytest.MonkeyPatch
) -> None:
    stub_discord(monkeypatch)
    resp = client.get("/auth/discord/callback", params={"code": "c", "state": "forged"})
    assert resp.status_code == 400
    assert resp.json() == {"error": "Bad login state"}


def test_callback_turns_away_a_non_member(
    client: Client, monkeypatch: pytest.MonkeyPatch
) -> None:
    stub_discord(monkeypatch, member_status=404)
    resp = client.get(
        "/auth/discord/callback",
        params={"code": "c", "state": start_state(client)},
    )
    assert resp.status_code == 403
    assert resp.json() == {"error": "Join the WC3 Gym Discord first"}


def test_a_member_logs_in_and_reads_me(
    client: Client, monkeypatch: pytest.MonkeyPatch
) -> None:
    stub_discord(monkeypatch)
    tokens = log_in(client)
    assert decode_token(tokens["refresh_token"])["type"] == "refresh"
    resp = client.get("/me", headers=headers(tokens))
    assert resp.status_code == 200
    assert resp.json() == {
        "discord_id": "42",
        "name": "Player",
        "avatar": "https://cdn.discordapp.com/avatars/42/abc.png",
        "role": "member",
        "user": None,
    }


def test_me_carries_the_linked_user(
    client: Client, monkeypatch: pytest.MonkeyPatch, seeded: dict[str, Any]
) -> None:
    stub_discord(monkeypatch, account={**ACCOUNT, "id": "1"})
    resp = client.get("/me", headers=headers(log_in(client)))
    assert resp.status_code == 200
    assert resp.json()["user"]["battleTag"] == "P1#1111"


def test_the_allowlist_makes_an_admin(
    client: Client, monkeypatch: pytest.MonkeyPatch
) -> None:
    stub_discord(monkeypatch, account={**ACCOUNT, "id": "220202568490418179"})
    resp = client.get("/me", headers=headers(log_in(client)))
    assert resp.json()["role"] == "admin"


def test_the_guild_owner_is_an_admin(
    client: Client, monkeypatch: pytest.MonkeyPatch
) -> None:
    stub_discord(monkeypatch, guild={**GUILD, "owner_id": "42"})
    resp = client.get("/me", headers=headers(log_in(client)))
    assert resp.json()["role"] == "admin"


def test_an_administrator_role_makes_an_admin(
    client: Client, monkeypatch: pytest.MonkeyPatch
) -> None:
    stub_discord(
        monkeypatch,
        member_roles=["boss"],
        guild={"owner_id": "999", "roles": [{"id": "boss", "permissions": "8"}]},
    )
    resp = client.get("/me", headers=headers(log_in(client)))
    assert resp.json()["role"] == "admin"


def test_the_admin_role_setting_makes_an_admin(
    client: Client, monkeypatch: pytest.MonkeyPatch, auth_headers: dict[str, str]
) -> None:
    resp = client.put(
        "/config/settings/admin_role",
        json={"value": "gym-admins"},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.json()
    stub_discord(monkeypatch, member_roles=["gym-admins"])
    resp = client.get("/me", headers=headers(log_in(client)))
    assert resp.json()["role"] == "admin"


def test_refresh_keeps_the_member_role(
    client: Client, monkeypatch: pytest.MonkeyPatch
) -> None:
    stub_discord(monkeypatch)
    tokens = log_in(client)
    resp = client.post(
        "/refresh", headers={"Authorization": f"Bearer {tokens['refresh_token']}"}
    )
    assert resp.status_code == 200
    claims = decode_token(resp.json()["access_token"])
    assert claims["role"] == "member"
    assert claims["name"] == "Player"


def test_a_member_token_is_no_admin_token(
    client: Client, monkeypatch: pytest.MonkeyPatch
) -> None:
    stub_discord(monkeypatch)
    resp = client.get("/config/koth/nightbot-token", headers=headers(log_in(client)))
    assert resp.status_code == 403
    assert resp.json() == {"error": "Admins only"}


def test_the_admin_token_login_still_admits(
    client: Client, auth_headers: dict[str, str]
) -> None:
    assert decode_token(auth_headers["Authorization"].split()[1])["role"] == "admin"
    resp = client.get("/me", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["role"] == "admin"
