"""The database engine and session factory for the whole process.

SQLAlchemy wants one Engine for each database for the life of the
application, with the session factory beside it at module level. Both are
safe to share between threads. A Session is not, so every caller opens its
own and drops it at the end of the call.

One Engine for each service would split the pool into pools that cannot
lend connections to each other, and that together allow far more
connections than the server accepts.

Each gunicorn worker is a process with a pool of its own, so
workers x 15 must stay under the max_connections of the server. MySQL 5.7
allows 151 by default, which leaves room for ten workers. Two things to
know before raising the worker count, which is 1 today:

  - On an empty database the workers race in init_schema, because
    create_all asks whether a table exists and then creates it. Start one
    worker first, or create the tables with a script.
  - Under --preload the workers inherit this engine, and a connection is a
    socket that two processes must not share. Each worker then has to call
    engine.dispose(close=False) in a post_fork hook.
"""

import os

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.database.model.DBModel import Base

# src/__init__.py loads the .env file before it imports this module.
DB_URL = os.getenv("DB_URL")
if not DB_URL:
    raise RuntimeError("DB_URL is not set. See the variable table in README.md.")

# The pool keeps the SQLAlchemy defaults: 5 connections, and 10 more in a
# burst. Both settings below are for MySQL, which drops an idle connection.
engine = create_engine(DB_URL, pool_pre_ping=True, pool_recycle=3600)

Session = sessionmaker(bind=engine)


def init_schema():
    """Create the tables that do not exist yet. Runs one time at start up."""
    Base.metadata.create_all(engine)

    # Start up is the only user of this connection, so give it back.
    engine.dispose()
