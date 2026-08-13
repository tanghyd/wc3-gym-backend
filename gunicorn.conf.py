"""Gunicorn settings for the backend.

Gunicorn reads this file on its own when it starts in the directory that
holds the file. The values below are the ones that the Dockerfile passed
before. To change one, set GUNICORN_CMD_ARGS, which gunicorn reads by
itself:

    GUNICORN_CMD_ARGS="--workers=4"

Read src/database/engine.py before a change to the number of workers.
Every worker is a process with a connection pool of its own, so the
workers multiply the number of database connections.
"""

bind = "0.0.0.0:5002"
workers = 1
timeout = 1250


def post_fork(server, worker):
    """Give each worker process its own database connections.

    A database connection is a socket, and two processes must never use
    the same socket. With --preload the parent process holds the engine
    and the worker inherits it. This hook drops the inherited connections
    in the worker and leaves the sockets of the parent open, so the worker
    opens fresh connections of its own.

    This hook must not import the application. Without --preload gunicorn
    runs this hook before the worker loads the application, so an import
    here would start the whole application inside the hook. The lookup in
    sys.modules therefore finds the engine only when the parent already
    loaded it, which is the only case that needs the call.
    """
    import sys

    engine_module = sys.modules.get("src.database.engine")
    if engine_module is not None:
        engine_module.dispose_engine(close=False)
