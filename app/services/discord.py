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


def authorize_url(state: str) -> str:
    """Where the browser goes to grant us the account's identity."""
    query = urllib.parse.urlencode(
        {
            "client_id": os.getenv("DISCORD_CLIENT_ID", ""),
            "redirect_uri": os.getenv("DISCORD_REDIRECT_URI", ""),
            "response_type": "code",
            "scope": "identify",
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


def identify(access_token: str) -> dict[str, Any]:
    """The Discord account behind that access token."""
    response = requests.get(
        f"{API_URL}/users/@me",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=REQUEST_TIMEOUT,
    )
    if not response.ok:
        raise ApiError(502, {"error": "Discord refused the login"})
    return dict(response.json())


def avatar_url(account: dict[str, Any]) -> str | None:
    """The account's avatar image, or None when it has the default one."""
    avatar = account.get("avatar")
    if not avatar:
        return None
    return f"https://cdn.discordapp.com/avatars/{account['id']}/{avatar}.png"


def _bot_get(path: str) -> requests.Response:
    return requests.get(
        f"{API_URL}{path}",
        headers={"Authorization": f"Bot {os.getenv('DISCORD_BOT_TOKEN', '')}"},
        timeout=REQUEST_TIMEOUT,
    )


def role_for(discord_id: str, admin_role: str | None = None) -> str:
    """The account's role, "admin" or "member"; a non-member is turned away."""
    guild_id = os.getenv("DISCORD_GUILD_ID", "")
    member = _bot_get(f"/guilds/{guild_id}/members/{discord_id}")
    if member.status_code == 404:
        raise ApiError(
            403, {"error": "No valid WC3 Gym server membership found for user"}
        )
    if not member.ok:
        raise ApiError(502, {"error": "Discord refused the membership check"})
    roles = set(member.json().get("roles", []))

    allowlist = os.getenv("ADMIN_DISCORD_IDS", "").replace(" ", "").split(",")
    if discord_id in allowlist:
        return "admin"
    if admin_role and admin_role in roles:
        return "admin"

    guild = _bot_get(f"/guilds/{guild_id}")
    if not guild.ok:
        return "member"
    body = guild.json()
    if str(body.get("owner_id")) == discord_id:
        return "admin"
    admin_roles = {
        role["id"]
        for role in body.get("roles", [])
        if int(role.get("permissions", 0)) & ADMINISTRATOR
    }
    return "admin" if roles & admin_roles else "member"
