"""The combined application that carries the FastAPI migration.

FastAPI owns the root and the unchanged Flask application is mounted
below it. Routers are matched first, so an API module moves frameworks by
being included here and deleted from Flask; every route not yet moved
falls through to Flask unchanged. When the last module has moved, the
mount and this docstring's second sentence go away.

The server calls the factory itself, as
`uvicorn --factory app.asgi:create_app`, so no application is built at
import.
"""

import logging
from contextlib import asynccontextmanager

import anyio.to_thread
from a2wsgi import WSGIMiddleware
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.dependencies import AuthError
from app.exceptions import DBException, NotFoundException
from app.main import create_app as create_flask_app

logger = logging.getLogger(__name__)

# Production has one CPU core and serves through one synchronous worker
# today, so one request at a time is the behaviour being preserved. This
# caps both thread pools below: FastAPI's own, and the mounted Flask
# app's.
MAX_CONCURRENT_REQUESTS = 1


@asynccontextmanager
async def _lifespan(app: FastAPI):
    limiter = anyio.to_thread.current_default_thread_limiter()
    limiter.total_tokens = MAX_CONCURRENT_REQUESTS
    yield


def create_app(db_url=None, flask_app=None):
    """Build the combined application: FastAPI at the root, Flask below.

    Reads the environment when the caller passes no db_url. Tests pass
    their already-built Flask application, because the engine and the
    blueprint attributes are process-global and must exist once.
    """
    flask_app = flask_app or create_flask_app(db_url)
    app = FastAPI(
        title="GNL Backend API",
        description="API for Gym Newbie League Backend Data",
        version="1.0.0",
        lifespan=_lifespan,
    )
    register_exception_handlers(app)
    app.mount("/", WSGIMiddleware(flask_app, workers=MAX_CONCURRENT_REQUESTS))
    return app


def register_exception_handlers(app: FastAPI) -> None:
    """The error responses the Flask routes produce, as global handlers.

    The {"error": str(exc)} body is a public contract: the frontend
    branches on `error.error`. NotFoundException answers 404, everything
    else 500, and str(exc) keeps the class-name prefix the per-route
    handlers produce today.
    """

    @app.exception_handler(NotFoundException)
    async def not_found(request: Request, exc: NotFoundException):
        logger.error(exc)
        return JSONResponse({"error": str(exc)}, status_code=404)

    @app.exception_handler(DBException)
    async def db_error(request: Request, exc: DBException):
        logger.error(exc)
        return JSONResponse({"error": str(exc)}, status_code=500)

    @app.exception_handler(AuthError)
    async def auth_error(request: Request, exc: AuthError):
        return JSONResponse({"msg": exc.message}, status_code=401)

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception):
        logger.error(exc)
        return JSONResponse({"error": str(exc)}, status_code=500)
