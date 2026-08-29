"""The Discord OAuth calls and the role a logged-in account gets."""

import os
import urllib.parse
from typing import Any

import requests

from app.core.exceptions import ApiError

API_URL = "https://discord.com/api/v10"

# Seconds a Discord call can hold the thread before it fails.
REQUEST_TIMEOUT = 10

# The Discord permission bit that makes a role a guild administrator.
ADMINISTRATOR = 0x8

# The account grants these: who it is, the guilds it is in, and its roles in one.
SCOPES = "identify guilds guilds.members.read"


def authorize_url(state: str) -> str:
    """Where the browser goes to grant us the account's identity."""
    query = urllib.parse.urlencode(
        {
            "client_id": os.getenv("DISCORD_CLIENT_ID", ""),
            "redirect_uri": os.getenv("DISCORD_REDIRECT_URI", ""),
            "response_type": "code",
            "scope": SCOPES,
            "state": state,
        }
    )
    return f"{API_URL}/oauth2/authorize?{query}"


def exchange_code(code: str) -> str:
    """The account's Discord access token, from the authorization code."""
    response = requests.post(
        f"{API_URL}/oauth2/token",
        data={
            "client_id": os.getenv("DISCORD_CLIENT_ID", ""),
            "client_secret": os.getenv("DISCORD_CLIENT_SECRET", ""),
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": os.getenv("DISCORD_REDIRECT_URI", ""),
        },
        timeout=REQUEST_TIMEOUT,
    )
    if not response.ok:
        raise ApiError(502, {"error": "Discord refused the login"})
    return str(response.json()["access_token"])


def _user_get(access_token: str, path: str) -> requests.Response:
    return requests.get(
        f"{API_URL}{path}",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=REQUEST_TIMEOUT,
    )


def identify(access_token: str) -> dict[str, Any]:
    """The Discord account behind that access token."""
    response = _user_get(access_token, "/users/@me")
    if not response.ok:
        raise ApiError(502, {"error": "Discord refused the login"})
    return dict(response.json())


def avatar_url(account: dict[str, Any]) -> str | None:
    """The account's avatar image, or None when it has the default one."""
    avatar = account.get("avatar")
    if not avatar:
        return None
    return f"https://cdn.discordapp.com/avatars/{account['id']}/{avatar}.png"


def role_for(access_token: str, discord_id: str, admin_role: str | None = None) -> str:
    """The account's role: "admin", "member", or "guest" outside the guild.

    Everything is read with the account's own token, so the app needs no bot
    in the guild.
    """
    guild_id = os.getenv("DISCORD_GUILD_ID", "")
    guilds = _user_get(access_token, "/users/@me/guilds")
    if not guilds.ok:
        raise ApiError(502, {"error": "Discord refused the membership check"})
    guild = next((row for row in guilds.json() if str(row.get("id")) == guild_id), None)
    if guild is None:
        # A guest logs in and sees the public pages; the routes of a player refuse it.
        return "guest"

    allowlist = os.getenv("ADMIN_DISCORD_IDS", "").replace(" ", "").split(",")
    if discord_id in allowlist:
        return "admin"
    if guild.get("owner") or int(guild.get("permissions", 0)) & ADMINISTRATOR:
        return "admin"
    if not admin_role:
        return "member"

    member = _user_get(access_token, f"/users/@me/guilds/{guild_id}/member")
    roles = set(member.json().get("roles", [])) if member.ok else set()
    return "admin" if admin_role in roles else "member"
