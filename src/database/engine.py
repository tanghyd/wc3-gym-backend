"""The database engine and the session factory for the whole process.

The SQLAlchemy documentation says to keep one Engine for each database
for the life of the application, and to keep the session factory next to
it at the module level. Both objects are factories, so any number of
functions and threads may use them at the same time. A Session is not,
because it holds one transaction and one connection, so every caller
opens its own session and drops it at the end of the call.

The Engine owns a connection pool. One Engine for each database service
would split the pool into many small pools that cannot lend connections
to each other, and together they would allow far more connections than
the database server accepts.

The pool keeps the SQLAlchemy defaults, which allow 5 connections and 10
more in a burst. Each gunicorn worker is a process with a pool of its
own, so the workers multiply that number:

    workers x 15 <= the max_connections of the server

MySQL 5.7 accepts 151 connections by default, which leaves room for ten
workers. The two settings below are not defaults, and both exist for
MySQL, which closes a connection that stays idle for a long time.

src/__init__.py loads the .env file before it imports this module.
"""

import logging
import os

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.database.model.DBModel import Base

logger = logging.getLogger(__name__)

DB_URL = os.getenv("DB_URL")
if not DB_URL:
    raise RuntimeError(
        "DB_URL is not set, so the application cannot reach the database. "
        "See the environment variable table in README.md."
    )

engine = create_engine(
    DB_URL,
    # Test a connection before use, so a connection that the server
    # dropped does not fail a request.
    pool_pre_ping=True,
    # Replace a connection after an hour, which stays below the default
    # wait_timeout of MySQL.
    pool_recycle=3600,
)

# The one session factory of the process. Every database service uses it.
# create_engine opens no connection, so nothing reaches the database until
# the first session runs the first statement.
Session = sessionmaker(bind=engine)


def init_schema():
    """Create the tables that do not exist yet.

    The application calls this one time at start up. Once the tables
    exist, this creates nothing.
    """
    Base.metadata.create_all(engine)

    # Give the connection back to the server. Start up is the only user of
    # it, and a gunicorn parent process with preload on would hold it open
    # and idle for as long as the application runs. The pool opens a new
    # connection when the first request needs one.
    engine.dispose()
    logger.debug("Database schema checked.")


def dispose_engine(close=True):
    """Empty the connection pool of this process.

    A worker process calls this with close set to false after a fork. A
    database connection is a socket, and two processes must never use the
    same socket. With close set to false the worker drops the inherited
    connections and opens its own, and it leaves the connections of the
    parent process open.

    The engine stays usable, because SQLAlchemy builds a new pool for it.
    """
    engine.dispose(close=close)
    logger.info("Database connection pool emptied.")
