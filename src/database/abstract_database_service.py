from abc import ABC, abstractmethod
from contextlib import contextmanager
import logging

from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker

from src.database.model.DBModel import Base
from custom_exceptions import DBException

logger = logging.getLogger(__name__)

class AbstractDatabaseService(ABC):
    def __init__(self, db_url):
        # Optimize connection pooling for better performance
        self.engine = create_engine(
            db_url,
            pool_size=10,              # Maintain 10 persistent connections
            max_overflow=20,           # Allow up to 20 extra connections during peak
            pool_pre_ping=True,        # Verify connections before using
            pool_recycle=3600,         # Recycle connections every hour
            echo=False                  # Disable SQL logging for performance
        )
        
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)

    @contextmanager
    def get_session(self):
        # The session commits when the block ends without an error,
        # rolls back when there is an error, and always closes.
        # Model helpers and service code must not commit; they flush.
        with self.Session() as session:
            try:
                with session.begin():
                    yield session
            except SQLAlchemyError as e:
                logger.error(f"Database error: {e}")
                raise DBException(f"Database error: {e}")

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
