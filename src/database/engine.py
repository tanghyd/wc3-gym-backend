"""One engine and one session factory for the whole process.

SQLAlchemy wants one Engine for each database for the life of the
application, with the session factory beside it at module level. Both are
safe to share between threads. A Session is not, so every caller opens its
own and drops it at the end of the call.

One Engine for each service would split the pool into pools that cannot
lend connections to each other.
"""

import os

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.database.model.DBModel import Base

# src/__init__.py loads the .env file before it imports this module.
DB_URL = os.getenv("DB_URL")
if not DB_URL:
    raise RuntimeError("DB_URL is not set. See the variable table in README.md.")

# Both settings are for MySQL, which drops a connection that stays idle.
engine = create_engine(DB_URL, pool_pre_ping=True, pool_recycle=3600)

Session = sessionmaker(bind=engine)


def init_schema():
    """Create the tables that do not exist yet. Runs one time at start up.

    This holds the application to one worker. create_all asks whether a
    table exists and then creates it, so two workers that start against an
    empty database race, and one stops with "table already exists".
    """
    Base.metadata.create_all(engine)

    # Start up is the only user of this connection, so give it back.
    engine.dispose()
