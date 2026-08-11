import logging
from src.database.abstract_database_service import AbstractDatabaseService
from src.database.model.DBSettings import DBSettings
from sqlalchemy.exc import SQLAlchemyError
from custom_exceptions import DBException
from src.dtos.settings_dto import SettingsDTO

logger = logging.getLogger(__name__)

class SettingsDBService(AbstractDatabaseService):
    
    def add(self, settings: SettingsDTO):
        """Add a new setting"""
        with self.get_session() as session:
            try:
                new_setting = DBSettings.add(session, settings.to_db_dict())
                if not new_setting:
                    raise DBException("Setting could not be created!")
                return SettingsDTO.from_dbsettings(new_setting)
            except SQLAlchemyError as e:
                logger.error(f"Database error adding setting: {e}")
                raise DBException(f"Database error: {e}")
    
    def update(self, settings: SettingsDTO):
        """Update a setting"""
        with self.get_session() as session:
            try:
                updated_setting = DBSettings.update(session, settings.id, **settings.to_db_dict())
                if not updated_setting:
                    raise DBException("Setting could not be updated!")
                return SettingsDTO.from_dbsettings(updated_setting)
            except SQLAlchemyError as e:
                logger.error(f"Database error updating setting: {e}")
                raise DBException(f"Database error: {e}")
    
    def delete(self, setting_id):
        """Delete a setting by id"""
        with self.get_session() as session:
            try:
                DBSettings.delete(session, setting_id)
            except SQLAlchemyError as e:
                logger.error(f"Database error deleting setting: {e}")
                raise DBException(f"Database error: {e}")
    
    def get(self, setting_id):
        """Get a setting by id"""
        with self.get_session() as session:
            try:
                setting = session.query(DBSettings).filter_by(id=setting_id).first()
                if not setting:
                    raise DBException(f"Setting with id '{setting_id}' not found")
                return SettingsDTO.from_dbsettings(setting)
            except SQLAlchemyError as e:
                logger.error(f"Database error getting setting: {e}")
                raise DBException(f"Database error: {e}")
    
    def getAll(self):
        """Get all settings"""
        with self.get_session() as session:
            try:
                result = []
                settings = DBSettings.getAll(session)
                for setting in settings:
                    result.append(SettingsDTO.from_dbsettings(setting))
                return result
            except SQLAlchemyError as e:
                logger.error(f"Database error getting all settings: {e}")
                raise DBException(f"Database error: {e}")
    
    def get_settings_dict(self):
        """Get all settings as a dictionary"""
        with self.get_session() as session:
            try:
                return DBSettings.get_all_as_dict(session)
            except SQLAlchemyError as e:
                logger.error(f"Database error getting settings dict: {e}")
                raise DBException(f"Database error: {e}")
    
    def get_by_key(self, key):
        """Get a setting by key (helper method for API)"""
        with self.get_session() as session:
            try:
                setting = DBSettings.get_by_key(session, key)
                if not setting:
                    raise DBException(f"Setting with key '{key}' not found")
                return SettingsDTO.from_dbsettings(setting)
            except SQLAlchemyError as e:
                logger.error(f"Database error getting setting by key: {e}")
                raise DBException(f"Database error: {e}")
