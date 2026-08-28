from datetime import datetime

from sqlalchemy import Index
from sqlmodel import Field, SQLModel

from app.models.base import DBModel
from app.models.enums import Race
from app.models.w3c_stats import W3CSyncResult


class W3CLadderMatchBase(SQLModel):
    w3c_match_id: str = Field(max_length=24)
    wc3_season: int
    # UTC, the shape the DATETIME columns hold
    start_time: datetime
    duration_s: int
    map_name: str | None = Field(default=None, max_length=50)
    # The race this player played, with a random pick resolved
    race: Race | None = None
    opp_battletag: str | None = Field(default=None, max_length=50)
    opp_race: Race | None = None
    won: bool
    mmr_before: int | None = None
    mmr_after: int | None = None


class W3CLadderMatch(W3CLadderMatchBase, DBModel, table=True):
    __tablename__ = "w3c_ladder_matches"
    # One row per player per match, and the season read pages by player and date
    __table_args__ = (
        Index(
            "uq_w3c_ladder_matches_match_user",
            "w3c_match_id",
            "user_id",
            unique=True,
        ),
        Index("ix_w3c_ladder_matches_user_id_start_time", "user_id", "start_time"),
    )

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id")


class W3CLadderMatchCreate(W3CLadderMatchBase):
    # The player this row belongs to; the sync service maps it to user_id
    battleTag: str


class LadderSyncResult(W3CSyncResult):
    """One chunk of a season sync, and where the next chunk starts."""

    total: int = 0
    next_offset: int | None = None
