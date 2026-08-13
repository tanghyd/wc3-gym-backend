from abc import ABC, abstractmethod
from contextlib import contextmanager
import logging

from sqlalchemy.exc import SQLAlchemyError

from src.database.engine import Session
from custom_exceptions import DBException

logger = logging.getLogger(__name__)


class AbstractDatabaseService(ABC):
    """Base class for the services that read and write the database.

    A service owns its queries. It does not own an engine and it does not
    own a connection pool. Every service shares the one engine and the one
    session factory of the process, which src/database/engine.py holds.
    """

    def __init__(self, *, session_factory=None):
        """Store the session factory that this service uses.

        The argument is keyword only. These services took a database URL
        before, so a caller that still passes one fails here with a clear
        TypeError, and not later on the first query.

        Args:
            session_factory: A factory to use instead of the factory of
                this process. A test passes its own factory to work on
                another database. Leave it empty in the application.
        """
        self.Session = session_factory or Session

    @contextmanager
    def get_session(self):
        """One transaction per call: commit on success, roll back on error,
        always close. Callers must not commit; to share a transaction, pass
        the session instead of opening a new one. Database errors become
        DBException here and nowhere else."""
        try:
            with self.Session.begin() as session:
                yield session
        except SQLAlchemyError as e:
            logger.exception("Database error")
            raise DBException(f"Database error: {e}") from e

    @abstractmethod
    def add(self, **kwargs):
        pass

    @abstractmethod
    def update(self, obj_id, **kwargs):
        pass

    @abstractmethod
    def delete(self, obj_id):
        pass

    @abstractmethod
    def get(self, obj_id):
        pass
