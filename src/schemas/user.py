from typing import Annotated

from src.database.model.DBEnums import Race
from src.schemas.base import APISchema, NoneToList
from src.schemas.season import Season
from src.schemas.user_team_season_stats import UserTeamSeasonStats
from src.schemas.w3c_stats import W3CStats

DB_FIELDS = {
    'id', 'name', 'battleTag', 'discordTag', 'discordId',
    'race', 'mmr', 'country', 'fantasy_tier',
}


class User(APISchema):
    id: int | None = None
    name: str | None = None
    battleTag: str | None = None
    discordTag: str | None = None
    discordId: str | None = None
    race: Race | str | None = None
    mmr: int | None = None
    country: str | None = None
    w3c_stats: Annotated[list[W3CStats], NoneToList] = []
    gnl_stats: Annotated[list[UserTeamSeasonStats], NoneToList] = []
    fantasy_tier: int | None = None
    signup_seasons: Annotated[list[Season], NoneToList] = []

    def to_db_dict(self):
        return self.model_dump(include=DB_FIELDS)

    @classmethod
    def from_dbuser(cls, user):
        if not user:
            return None

        return cls(
            id=user.id,
            name=user.name,
            battleTag=user.battleTag,
            discordTag=user.discordTag,
            discordId=user.discordId,
            race=user.race,
            mmr=user.mmr,
            country=user.country,
            w3c_stats=[s for s in (W3CStats.from_dbw3cstats(stat) for stat in user.w3c_stats) if s] if user.w3c_stats else [],
            gnl_stats=[s for s in (UserTeamSeasonStats.from_db_user_team_season(stat) for stat in user.team_seasons) if s] if user.team_seasons else [],
            fantasy_tier=user.fantasy_tier,
            signup_seasons=[s for s in (Season.from_dbseason_reduced(signup.season) for signup in user.signup_seasons) if s] if user.signup_seasons else [],
        )

    @staticmethod
    def schema():
        return {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "User's Name"
                },
                "battleTag": {
                    "type": "string",
                    "description": "User's BattleTag"
                },
                "discordId":{
                    "type": "string",
                    "description": "User's DiscordId"
                },
                "discordTag": {
                    "type": "string",
                    "description": "User's DiscordTag"
                },
                "race": {
                    "type": "string",
                    "description": "User's Race"
                },
                "mmr": {
                    "type": "integer",
                    "description": "User's MMR"
                },
                "country": {
                    "type": "string",
                    "description": "User's Country"
                },
                "fantasy_tier": {
                    "type": "integer",
                    "description": "fantasy tier"
                }
            },
            "required": ["name", "battleTag", "discordId", "discordTag"]
        }
