"""Shared Pydantic base class and validation helpers for the API schemas.

These schemas replace the hand-written DTO classes that lived in src/dtos.
They keep the same class names, constructor style and to_dict()/to_db_dict()
surface so the api/service/database layers work unchanged, while giving us
real Pydantic models for a future FastAPI port.

The JSON produced by to_dict() is a public contract consumed by the
warcraft-gym.com frontend pages - field names and value shapes must not
change.
"""
import enum
import numbers
from datetime import date, datetime
from typing import Annotated, Any

from pydantic import BaseModel, BeforeValidator, ConfigDict, PlainSerializer


def _enum_to_value(value: Any) -> Any:
    return value.value if isinstance(value, enum.Enum) else value


def _none_to_list(value: Any) -> Any:
    if value is None:
        return []
    if isinstance(value, list):
        return [item for item in value if item is not None]
    return value


def _int_to_str(value: Any) -> Any:
    # numbers.Integral also matches numpy integer scalars, which the xlsx
    # import passes for Discord role IDs (pandas reads the column as int64).
    if isinstance(value, numbers.Integral) and not isinstance(value, bool):
        return str(int(value))
    return value


def _empty_to_none(value: Any) -> Any:
    if isinstance(value, list):
        value = [item for item in value if item is not None]
    return value if value else None


# Date/datetime fields must serialize to JSON exactly like the old DTOs'
# `.isoformat()` calls (pydantic's default differs for timezone-aware values:
# 'Z' instead of '+00:00'). In python mode (to_db_dict) the objects pass
# through untouched, so the DB layer receives real date/datetime values.
IsoDateTime = Annotated[
    datetime,
    PlainSerializer(lambda v: v.isoformat(), return_type=str, when_used='json-unless-none'),
]
IsoDate = Annotated[
    date,
    PlainSerializer(lambda v: v.isoformat(), return_type=str, when_used='json-unless-none'),
]

# Race columns hold Race enum members when read via SQLAlchemy; the API always
# exposed the plain value (via the app's custom JSON provider), so normalize
# to the value at validation time.
EnumValue = BeforeValidator(_enum_to_value)
# Fields the old DTOs serialized as 'x if x else []'.
NoneToList = BeforeValidator(_none_to_list)
# Fields the old DTOs serialized as 'x if x else None' (empty list -> null).
EmptyToNone = BeforeValidator(_empty_to_none)
# String fields that sometimes receive whole numbers (Discord role IDs from
# the xlsx import). The old DTOs passed them through and MySQL stored the
# digits; convert to the same digit string up front.
IntToStr = BeforeValidator(_int_to_str)


class APISchema(BaseModel):
    # validate_assignment: the service layer mutates these objects in place
    # (e.g. `map.id = None`, `team.player_by_season = {...}`), and those
    # values must go through the same validators as constructor input.
    model_config = ConfigDict(extra='ignore', validate_assignment=True)

    def __init__(self, data: dict | None = None, **kwargs):
        # The old DTOs were constructed as `SomeDTO(request.json)`; keep that
        # calling convention alongside regular keyword construction.
        super().__init__(**(data if data is not None else kwargs))

    def to_dict(self) -> dict:
        return self.model_dump(mode='json')
