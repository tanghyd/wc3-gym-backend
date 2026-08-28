from datetime import datetime
from typing import Annotated

from sqlalchemy import Index
from sqlmodel import Field, SQLModel

from app.core.achievements import Achievement
from app.models.base import DBModel
from app.models.enums import Race
from app.models.types import EnumValue, IsoDate
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


class LadderMmr(SQLModel):
    """Where the MMR of the window opened, its range, and where it stands."""

    start: int | None = None
    min: int | None = None
    max: int | None = None
    current: int | None = None


class LadderDay(SQLModel):
    """One day of one player: wins, losses and the MMR he ended the day on."""

    d: IsoDate
    w: int = 0
    l: int = 0  # the client draws w and l as one bar per day
    mmr: int | None = None


class LadderPlayer(SQLModel):
    """One player's ladder record over the scope the route was asked for."""

    id: int
    name: str | None = None
    battleTag: str | None = None
    race: Annotated[str | None, EnumValue] = None
    # Ladder points plus achievement points, the total wc3.no publishes
    points: int = 0
    # The 3/1 rule on its own, without the achievements
    ladder_points: int = 0
    wins: int = 0
    losses: int = 0
    games: int = 0
    mmr: LadderMmr = LadderMmr()
    per_day: list[LadderDay] = []
    # Wins and losses against each race, keyed by the race the opponent played
    vs_race: dict[str, list[int]] = {}
    # The rules of core.achievements this player earned, worth most first
    achievements: list[Achievement] = []


class LadderTeam(SQLModel):
    """One team of the season, with the ladder record of every player on it."""

    id: int
    name: str | None = None
    points: int = 0
    ladder_points: int = 0
    games: int = 0
    players: list[LadderPlayer] = []


class LadderSeason(SQLModel):
    """The season the ladder answer covers."""

    id: int
    start_date: IsoDate | None = None
    end_date: IsoDate | None = None
    # The newest ladder_synced_at among the players signed up
    synced_at: datetime | None = None


class SeasonLadder(SQLModel):
    """The GNL > Ladder page: one season, its teams and its players."""

    season: LadderSeason
    # Distinct matches, so a match between two GNL players counts once
    total_games: int = 0
    # 7 weekdays by 24 hours, UTC, distinct matches. Row 0 is Sunday.
    by_hour: list[list[int]] = []
    teams: list[LadderTeam] = []


class LadderMatchPublic(SQLModel):
    """One match of the player's list."""

    w3c_match_id: str
    start_time: datetime
    duration_s: int
    map_name: str | None = None
    race: Annotated[str | None, EnumValue] = None
    opp_battletag: str | None = None
    opp_race: Annotated[str | None, EnumValue] = None
    won: bool
    mmr_before: int | None = None
    mmr_after: int | None = None
    # The GNL user the opponent is, null when he plays no GNL
    opp_user_id: int | None = None


class UserLadder(LadderPlayer):
    """One player's record, and the page of matches behind it."""

    matches: list[LadderMatchPublic] = []
