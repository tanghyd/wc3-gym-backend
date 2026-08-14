import logging

from app.exceptions import DBException
from app.models.relationships import DBTeamSeason
from app.schemas.season_info import SeasonInfo
from app.services.base import BaseService

logger = logging.getLogger(__name__)


class TeamSeasonService(BaseService):
    # add, delete and get build an exception and hand it back as the result.
    # They are typed as they behave; see the note in the pull request.
    def add(self) -> Exception:
        return Exception("Method not available")

    def update(self, team_id: int, season_info: SeasonInfo) -> SeasonInfo | None:
        with self.get_session() as session:
            db_season_info = DBTeamSeason.updateSeasonInfo(
                session, season_info.season_id, team_id, **season_info.to_db_dict()
            )
            if not db_season_info:
                raise DBException("Season could not be updated!")
            return SeasonInfo.from_dbseasoninfo(db_season_info)

    def delete(self) -> Exception:
        return Exception("Method not available")

    def get(self) -> Exception:
        return Exception("Method not available")

    def update_team_season(
        self, team_id: int, season_info: SeasonInfo
    ) -> SeasonInfo | None:
        return self.update(team_id, season_info)
