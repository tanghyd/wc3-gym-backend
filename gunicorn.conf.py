"""Gunicorn settings for the backend.

Gunicorn reads this file on its own when it starts in the directory that
holds the file. The defaults match the values that the Dockerfile used
before, so the behaviour does not change until an operator sets one of
the environment variables.

Read src/database/engine.py before a change to GUNICORN_WORKERS. Every
worker is a process with its own connection pool, so the number of
workers multiplies the number of database connections:

    workers x (DB_POOL_SIZE + DB_MAX_OVERFLOW) <= max_connections
"""

import os


def _int_env(name, default):
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _bool_env(name, default):
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


bind = os.getenv("GUNICORN_BIND", "0.0.0.0:5002")
workers = _int_env("GUNICORN_WORKERS", 1)
timeout = _int_env("GUNICORN_TIMEOUT", 1250)

# When preload is on, the parent process imports the application one time
# and the workers inherit it. This saves memory, and post_fork below keeps
# the database connections correct.
preload_app = _bool_env("GUNICORN_PRELOAD", False)


def post_fork(server, worker):
    """Give each worker process its own database connections.

    A database connection is a socket, and two processes must never use
    the same socket. With preload on, the parent process may already hold
    connections that the worker inherits. This call drops the inherited
    connections in the worker and leaves the sockets of the parent open,
    so the worker opens fresh connections of its own.

    The call does nothing when the worker has no engine yet, so it is
    safe with preload off as well.
    """
    from src.database.engine import dispose_engine

    dispose_engine(close=False)
