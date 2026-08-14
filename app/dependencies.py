"""FastAPI dependencies shared by the routers."""

import os
from typing import Annotated

import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer


class AuthError(Exception):
    """A request without a valid admin access token. Answered as 401 with
    the {"msg": ...} body flask_jwt_extended sends, so clients see the
    same auth errors on both frameworks."""

    def __init__(self, message):
        super().__init__(message)
        self.message = message


_bearer = HTTPBearer(auto_error=False)


def require_admin(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> str:
    """Validate the admin access token that /login issues.

    Accepts exactly the tokens flask_jwt_extended mints: signed with
    JWT_SECRET_KEY using JWT_ALGORITHM, carrying type "access". The same
    client token works on both frameworks during the migration.
    """
    if credentials is None:
        raise AuthError("Missing Authorization Header")
    try:
        claims = jwt.decode(
            credentials.credentials,
            os.getenv("JWT_SECRET_KEY"),
            algorithms=[os.getenv("JWT_ALGORITHM", "HS256")],
        )
    except jwt.InvalidTokenError as e:
        raise AuthError(str(e)) from e
    if claims.get("type") != "access":
        raise AuthError("Only non-refresh tokens are allowed")
    return claims["sub"]


RequireAdmin = Annotated[str, Depends(require_admin)]
