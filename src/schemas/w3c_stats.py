from src.database.model.DBEnums import Race
from src.schemas.base import APISchema

DB_FIELDS = {
    'wc3_season', 'wins', 'losses', 'games', 'mmr',
    'winrate', 'race', 'league', 'user_id',
}


class W3CStats(APISchema):
    id: int | None = None
    wc3_season: int | None = None
    wins: int | None = None
    losses: int | None = None
    games: int | None = None
    mmr: int | None = None
    winrate: float | None = None
    # Race member when loaded from the DB / w3champions sync, plain string
    # from request JSON - exactly like the old DTO. Services compare members.
    race: Race | str | None = None
    league: int | None = None
    user_id: int | None = None

    def to_db_dict(self):
        return self.model_dump(include=DB_FIELDS)

    @classmethod
    def from_dbw3cstats(cls, stats):
        return cls(
            id=stats.id,
            wc3_season=stats.wc3_season,
            wins=stats.wins,
            losses=stats.losses,
            games=stats.games,
            mmr=stats.mmr,
            winrate=stats.winrate,
            race=stats.race,
            league=stats.league,
            user_id=stats.user_id,
        )

    @staticmethod
    def schema():
        return {
            "type": "object",
            "properties": {
                "wc3_season": {
                    "type": "integer",
                    "description": "Season Number"
                },
                "wins": {
                    "type": "integer",
                    "description": "Number of wins"
                },
                "losses": {
                    "type": "integer",
                    "description": "Number of losses"
                },
                "games": {
                    "type": "intger",
                    "description": "Number of games"
                },
                "mmr": {
                    "type": "integer",
                    "description": "User's MMR"
                },
                "winrate": {
                    "type": "float",
                    "description": "Percentage of won games"
                },
                "race": {
                    "type": "string",
                    "description": "Race of the stats"
                },
                 "league": {
                    "type": "integer",
                    "description": "Number of the league"
                },
                "user_id": {
                    "type": "string",
                    "description": "User's Id"
                }
            }
        }
