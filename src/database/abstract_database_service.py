from abc import ABC, abstractmethod
from contextlib import contextmanager

from src.database.engine import session_scope


class AbstractDatabaseService(ABC):
    """Base class for the services that read and write the database.

    A service owns its queries. It does not own an engine and it does not
    own a connection pool. Every service shares the one engine and the one
    session factory of the process, which src/database/engine.py holds.
    """

    def __init__(self, *, session_factory=None):
        """Store the session factory that this service uses.

        The argument is keyword only. These services took a database URL
        before. A caller that still passes one now fails here, with a
        clear TypeError, instead of much later on the first query.

        Args:
            session_factory: A factory to use instead of the factory of
                this process. Tests pass their own factory to work on
                another database. Leave it empty in the application.
        """
        self._session_factory = session_factory

    @contextmanager
    def get_session(self):
        """One transaction for each call.

        The block commits on success, rolls back on error, and always
        closes the session. Callers must not commit. To share a
        transaction, pass the session instead of opening a new one.
        Database errors become DBException in session_scope and nowhere
        else.
        """
        with session_scope(self._session_factory) as session:
            yield session

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
