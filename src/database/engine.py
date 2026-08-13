"""Database engine and session factory for the whole process.

The SQLAlchemy documentation says to keep one Engine for each database
for the life of the application, and to keep the session factory next to
it in the module scope. Both objects are factories, so any number of
functions and threads can use them at the same time.

The Engine owns a connection pool. One Engine for each database service
would split the pool into many small pools. Those pools cannot lend
connections to each other, and together they would allow far more
connections than the database server accepts.

A Session is different. A Session holds one transaction and one
connection, so it is not safe to share. Every caller must open its own
session with session_scope() and must not keep the session after the
block ends.

Connection budget:

    gunicorn workers x (DB_POOL_SIZE + DB_MAX_OVERFLOW) <= max_connections

MySQL 5.7 accepts 151 connections by default. The default values below
allow 15 connections for each worker process.

The engine is built on first use, not on import. The application loads
the .env file after it imports these modules, so an engine built during
import would not see the values from that file.
"""

import logging
import os
import threading
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker

from custom_exceptions import DBException
from src.database.model.DBModel import Base

logger = logging.getLogger(__name__)

# Guards the build of the engine and the session factory. It is an RLock
# because the build of the session factory asks for the engine while it
# holds the lock.
_lock = threading.RLock()

_engine = None
_session_factory = None


def _int_env(name, default):
    """Read a whole number from the environment, or return the default."""
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw)
    except ValueError:
        logger.warning(
            "%s is not a whole number: %r. The application uses %d.", name, raw, default
        )
        return default


def _bool_env(name, default):
    """Read a true or false value from the environment."""
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _build_engine():
    """Build the engine from the environment variables."""
    db_url = os.getenv("DB_URL")
    if not db_url:
        raise RuntimeError(
            "DB_URL is not set, so the application cannot reach the database. "
            "See the environment variable table in README.md."
        )

    pool_size = _int_env("DB_POOL_SIZE", 5)
    max_overflow = _int_env("DB_MAX_OVERFLOW", 10)

    engine = create_engine(
        db_url,
        # Connections that the pool keeps open between requests.
        pool_size=pool_size,
        # Extra connections for a burst. The pool closes them again when
        # the burst ends.
        max_overflow=max_overflow,
        # Seconds to wait for a free connection before the request fails.
        pool_timeout=_int_env("DB_POOL_TIMEOUT", 30),
        # Replace a connection after this many seconds. The value must
        # stay below the wait_timeout of the MySQL server.
        pool_recycle=_int_env("DB_POOL_RECYCLE", 3600),
        # Test a connection before use, because MySQL closes connections
        # that stay idle for a long time.
        pool_pre_ping=True,
        echo=_bool_env("DB_ECHO", False),
    )

    logger.info(
        "Database engine ready. The process allows up to %d connections "
        "(pool size %d plus overflow %d).",
        pool_size + max_overflow,
        pool_size,
        max_overflow,
    )
    return engine


def get_engine():
    """Return the engine of this process, and build it on first use.

    create_engine() does not open a connection. The pool opens the first
    connection when a session runs the first statement.
    """
    global _engine
    if _engine is None:
        with _lock:
            if _engine is None:
                _engine = _build_engine()
    return _engine


def get_session_factory():
    """Return the session factory of this process.

    Every database service uses this one factory. Do not build another
    factory, and do not build another engine.
    """
    global _session_factory
    if _session_factory is None:
        with _lock:
            if _session_factory is None:
                _session_factory = sessionmaker(bind=get_engine())
    return _session_factory


@contextmanager
def session_scope(session_factory=None):
    """Run one transaction and give the caller its session.

    The block commits when it ends without an error, rolls back when the
    caller raises, and closes the session in both cases. Callers must not
    commit. To share one transaction between two services, pass the
    session to the second service instead of opening a new one.

    This function turns a database error into a DBException. No other
    place in the application may do that.

    Args:
        session_factory: A factory to use instead of the factory of this
            process. Tests use this to work on another database.
    """
    factory = session_factory or get_session_factory()
    try:
        with factory.begin() as session:
            yield session
    except SQLAlchemyError as e:
        logger.exception("Database error")
        raise DBException(f"Database error: {e}") from e


def init_schema():
    """Create the tables that do not exist yet.

    The application calls this one time at start up. Set DB_CREATE_ALL to
    false when another tool owns the schema, so that the application does
    not need rights to change tables.
    """
    if not _bool_env("DB_CREATE_ALL", True):
        logger.info("DB_CREATE_ALL is false, so the application creates no tables.")
        return
    Base.metadata.create_all(get_engine())
    logger.debug("Database schema checked.")


def dispose_engine(close=True):
    """Empty the connection pool of this process.

    A worker process calls this with close set to false after a fork. A
    connection is a socket, and two processes must never use the same
    socket. With close set to false the worker drops the inherited
    connections and opens its own, and it leaves the connections of the
    parent process open.

    The engine stays usable. SQLAlchemy builds a new pool for it.
    """
    if _engine is None:
        return
    _engine.dispose(close=close)
    logger.info("Database connection pool emptied.")
