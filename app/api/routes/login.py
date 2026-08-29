import os
import urllib.parse
from typing import Any

import jwt
from fastapi import APIRouter
from fastapi.responses import RedirectResponse

from app.api.deps import (
    RequireMember,
    RequireRefresh,
    SettingsServiceDep,
    UserServiceDep,
)
from app.core.exceptions import ApiError
from app.core.security import (
    create_access_token,
    create_refresh_token,
    create_state_token,
    decode_token,
)
from app.models.login import LoginRequest
from app.services import discord

router = APIRouter(tags=["Authentication"])


@router.get("/")
def index() -> RedirectResponse:
    """Send the browser to the API documentation."""
    return RedirectResponse("/docs", status_code=302)


@router.post("/login")
def login(data: LoginRequest) -> dict[str, str]:
    """Exchange the admin token for an access token and a refresh token."""
    token_time = int(os.getenv("TOKEN_TIME", "60"))
    refresh_token_time = int(os.getenv("REFRESH_TOKEN_TIME", "300"))
    if data.token != os.getenv("ADMIN_TOKEN"):
        raise ApiError(401, {"error": "Bad admin token"})
    return {
        "access_token": create_access_token("admin", token_time),
        "refresh_token": create_refresh_token("admin", refresh_token_time),
    }


@router.get("/auth/discord/start")
def discord_start() -> RedirectResponse:
    """Send the browser to Discord, carrying a state we can verify."""
    return RedirectResponse(
        discord.authorize_url(create_state_token()), status_code=302
    )


@router.get("/auth/discord/callback")
def discord_callback(
    code: str, state: str, settings_service: SettingsServiceDep
) -> RedirectResponse:
    """Turn the Discord code into our tokens and hand them to the frontend."""
    try:
        claims = decode_token(state)
    except jwt.InvalidTokenError as e:
        raise ApiError(400, {"error": "Bad login state"}) from e
    if claims.get("type") != "state":
        raise ApiError(400, {"error": "Bad login state"})

    account = discord.identify(discord.exchange_code(code))
    admin_role = settings_service.get_settings_dict().get("admin_role")
    identity = str(account["id"])
    extra = {
        "role": discord.role_for(identity, admin_role),
        "name": account.get("global_name") or account.get("username"),
        "avatar": discord.avatar_url(account),
    }
    tokens = urllib.parse.urlencode(
        {
            "access_token": create_access_token(
                identity, int(os.getenv("TOKEN_TIME", "60")), **extra
            ),
            "refresh_token": create_refresh_token(
                identity, int(os.getenv("REFRESH_TOKEN_TIME", "300")), **extra
            ),
        }
    )
    frontend_url = os.getenv("FRONTEND_URL", "")
    return RedirectResponse(f"{frontend_url}#/auth?{tokens}", status_code=302)


@router.get("/me")
def me(claims: RequireMember, user_service: UserServiceDep) -> dict[str, Any]:
    """The logged-in account and the users row linked to its Discord id."""
    users = user_service.find_by_discord_id(claims["sub"])
    return {
        "discord_id": claims["sub"],
        "name": claims.get("name"),
        "avatar": claims.get("avatar"),
        "role": claims.get("role", "admin"),
        "user": users[0] if users else None,
    }


@router.post("/refresh")
def refresh(
    claims: RequireRefresh, settings_service: SettingsServiceDep
) -> dict[str, Any]:
    """Exchange a refresh token for a new access token."""
    token_time = int(os.getenv("TOKEN_TIME", "60"))
    identity = claims["sub"]
    role = claims.get("role", "admin")
    if identity.isdigit():
        # A Discord subject: the roles may have changed since the login.
        role = discord.role_for(
            identity, settings_service.get_settings_dict().get("admin_role")
        )
    new_access_token = create_access_token(
        identity,
        token_time,
        role=role,
        name=claims.get("name"),
        avatar=claims.get("avatar"),
    )
    return {"access_token": new_access_token}
