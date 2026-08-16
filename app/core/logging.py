"""The request id and the one log line per request.

Every log record carries a request id. The id comes from a ContextVar
that the middleware sets once per request, and a logging filter copies it
onto the record. The filter answers "-" when no request is active, so a
record from startup, from Alembic, from a test or from the import thread
formats with the same format string.
"""

import logging
import time
from contextvars import ContextVar
from uuid import uuid4

from starlette.types import ASGIApp, Message, Receive, Scope, Send

logger = logging.getLogger(__name__)

LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s [%(request_id)s] %(message)s"

_request_id: ContextVar[str] = ContextVar("request_id")


def current_request_id() -> str:
    """The id of the request in this context, or "-" outside a request."""
    return _request_id.get("-")


class RequestIdFilter(logging.Filter):
    """Puts the request id on every record that reaches the handler."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = current_request_id()
        return True


request_id_filter = RequestIdFilter()


class RequestLogMiddleware:
    """Sets the request id, measures the request, and logs one line.

    A pure ASGI class, like CORSMiddleware. It adds no header and it
    changes no body.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        _request_id.set(uuid4().hex[:8])
        started = time.perf_counter()
        status = 500  # the value that stands if the application raises

        async def send_status(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, send_status)
        finally:
            query = scope.get("query_string", b"").decode("latin-1")
            path = f"{scope['path']}?{query}" if query else scope["path"]
            logger.info(
                "request id=%s method=%s path=%s status=%d dur_ms=%.1f",
                current_request_id(),
                scope["method"],
                path,
                status,
                (time.perf_counter() - started) * 1000,
            )
