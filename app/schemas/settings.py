from typing import TYPE_CHECKING, Annotated, Any, Self

from app.schemas.base import APISchema, NumToStr

if TYPE_CHECKING:
    from app.models.settings import DBSettings



class Settings(APISchema):
    id: int | None = None
    key: str | None = None
    # Settings values are stored as strings but callers pass numbers too.
    value: Annotated[str | None, NumToStr] = None
    description: str | None = None

    @classmethod
    def from_dbsettings(cls, db_settings: "DBSettings | None") -> Self | None:
        """Create DTO from database model"""
        if not db_settings:
            return None
        return cls(
            id=db_settings.id,
            key=db_settings.key,
            value=db_settings.value,
            description=db_settings.description,
        )

    def to_db_dict(self) -> dict[str, Any]:
        """Convert DTO to dictionary for database operations"""
        return self.model_dump(
            include={"key", "value", "description"}, exclude_none=True
        )
