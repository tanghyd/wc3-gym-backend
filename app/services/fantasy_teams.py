import logging

from sqlalchemy import select
from sqlalchemy.orm import joinedload

from app.exceptions import DBException, NotFoundException
from app.models.fantasy_team import DBFantasyTeam
from app.models.relationships import DBFantasyTeamPlayer
from app.schemas.fantasy_team import FantasyTeam
from app.services.base import BaseService
from app.utils.query_util import QueryElement, QueryUtil

logger = logging.getLogger(__name__)


class FantasyTeamService(BaseService):
    def add(self, fantasy_team: FantasyTeam) -> FantasyTeam:
        with self.get_session() as session:
            db_fantasy_team = DBFantasyTeam.add(session, fantasy_team.to_db_dict())
            if not db_fantasy_team:
                raise DBException("FantasyTeam could not be created!")
            return FantasyTeam.from_dbfantasyteam(db_fantasy_team)

    def update(self, fantasy_team: FantasyTeam) -> FantasyTeam:
        with self.get_session() as session:
            db_fantasy_team = DBFantasyTeam.update(
                session, fantasy_team.id, **fantasy_team.to_db_dict()
            )
            if not db_fantasy_team:
                raise DBException("Fantasy Team could not be updated!")
            return FantasyTeam.from_dbfantasyteam(db_fantasy_team)

    def delete(self, fantasy_team_id: int) -> None:
        with self.get_session() as session:
            DBFantasyTeam.delete(session, fantasy_team_id)

    def get(self, fantasy_team_id: int) -> FantasyTeam:
        with self.get_session() as session:
            fteam = session.get(DBFantasyTeam, fantasy_team_id)
            if not fteam:
                raise DBException("Fantasy Team could not be found")
            return FantasyTeam.from_dbfantasyteam(fteam)

    def getAll(self) -> list[FantasyTeam]:
        with self.get_session() as session:
            result: list[FantasyTeam] = []
            fteams = DBFantasyTeam.getAll(session)
            for fteam in fteams:
                result.append(FantasyTeam.from_dbfantasyteam(fteam))
            return result

    def search(self, query: QueryElement | None) -> list[FantasyTeam]:
        with self.get_session() as session:
            result: list[FantasyTeam] = []
            filter = QueryUtil.convertQueryToDBFilter(DBFantasyTeam, query)
            if filter is None:
                logger.debug(f"No fantasy team found by searchcriteria: {query}")
                return result
            # Eager load only the relations the DTO reads
            fteams = (
                session.scalars(
                    select(DBFantasyTeam)
                    .options(
                        joinedload(DBFantasyTeam.season).noload("*"),
                        joinedload(DBFantasyTeam.drafted_team).noload("*"),
                        joinedload(DBFantasyTeam.captain).noload("*"),
                        joinedload(DBFantasyTeam.drafted_players)
                        .joinedload(DBFantasyTeamPlayer.users)
                        .noload("*"),
                    )
                    .where(filter)
                )
                .unique()
                .all()
            )
            if not fteams:
                logger.debug(f"No fantasy team found by searchcriteria: {query}")
                return result
            for fteam in fteams:
                result.append(FantasyTeam.from_dbfantasyteam(fteam))
            return result

    def addPlayers(self, team_id: int, player_ids: list[int]) -> FantasyTeam:
        with self.get_session() as session:
            fteam = DBFantasyTeam.addPlayers(session, team_id, player_ids)
            if not fteam:
                raise DBException("Fantasy Team could not be updated!")
            return FantasyTeam.from_dbfantasyteam(fteam)

    def removePlayers(self, team_id: int, player_ids: list[int]) -> FantasyTeam:
        with self.get_session() as session:
            team = DBFantasyTeam.removePlayers(session, team_id, player_ids)
            if not team:
                raise DBException("Fantasy Team could not be updated!")
            return FantasyTeam.from_dbfantasyteam(team)

    def create_fantasy_team(self, team: FantasyTeam) -> FantasyTeam:
        team.id = None
        return self.add(team)

    def update_fantasy_team(self, team_id: int, team: FantasyTeam) -> FantasyTeam:
        team.id = team_id
        return self.update(team)

    def delete_fantasy_team(self, team_id: int) -> None:
        self.delete(team_id)

    def get_fantasy_team(self, team_id: int) -> FantasyTeam:
        team_data = self.get(team_id)
        if not team_data:
            raise NotFoundException(f"Fantasy Team not found by Id: {team_id}")
        return team_data

    def getAll_fantasy_teams(self) -> list[FantasyTeam]:
        return self.getAll()

    def search_fantasy_teams(self, query: QueryElement | None) -> list[FantasyTeam]:
        return self.search(query)

    def addFantasyPlayers(self, team_id: int, players: list[int]) -> FantasyTeam:
        return self.addPlayers(team_id, players)

    def removeFantasyPlayers(self, team_id: int, players: list[int]) -> FantasyTeam:
        return self.removePlayers(team_id, players)
