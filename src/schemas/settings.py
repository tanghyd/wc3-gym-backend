from src.schemas.base import APISchema


class Settings(APISchema):
    id: int | None = None
    key: str | None = None
    value: str | None = None
    description: str | None = None

    @classmethod
    def from_dbsettings(cls, db_settings):
        """Create DTO from database model"""
        if not db_settings:
            return None
        return cls(
            id=db_settings.id,
            key=db_settings.key,
            value=db_settings.value,
            description=db_settings.description,
        )

    def to_db_dict(self):
        """Convert DTO to dictionary for database operations"""
        return self.model_dump(
            include={'key', 'value', 'description'}, exclude_none=True
        )
