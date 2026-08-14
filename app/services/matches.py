import logging

from sqlalchemy import select
from sqlalchemy.orm import joinedload

from app.exceptions import DBException, NotFoundException
from app.models.match import DBMatch
from app.schemas.match import Match
from app.services.base import BaseService
from app.utils.query_util import QueryElement, QueryUtil

logger = logging.getLogger(__name__)


class MatchService(BaseService):
    def add(self, match: Match) -> Match:
        with self.get_session() as session:
            db_match = DBMatch.add(session, match.to_db_dict())
            if not db_match:
                logger.error("Match could not be created!")
                raise DBException("Match could not be created!")
            return Match.from_dbmatch(db_match)

    def update(self, match_id: int, match: Match) -> Match:
        with self.get_session() as session:
            db_match = DBMatch.update(session, match_id, **match.to_db_dict())
            if not db_match:
                logger.error("Match could not be updated!")
                raise DBException("Match could not be updated!")
            return Match.from_dbmatch(db_match)

    def delete(self, match_id: int) -> None:
        with self.get_session() as session:
            DBMatch.delete(session, match_id)

    def get(self, match_id: int) -> Match:
        with self.get_session() as session:
            # Eager load related entities, disable nested loading
            match = (
                session.scalars(
                    select(DBMatch)
                    .options(
                        joinedload(DBMatch.team1).noload("*"),
                        joinedload(DBMatch.team2).noload("*"),
                        joinedload(DBMatch.season).noload("*"),
                        joinedload(DBMatch.fixed_map),
                    )
                    .where(DBMatch.id == match_id)
                    .limit(1)
                )
                .unique()
                .first()
            )
            if not match:
                logger.error("Match could not be found!")
                raise DBException("Match could not be found!")
            return Match.from_dbmatch(match)

    def search(self, query: QueryElement | None) -> list[Match]:
        with self.get_session() as session:
            result: list[Match] = []
            filter = QueryUtil.convertQueryToDBFilter(DBMatch, query)
            # Eager load only what we need, explicitly disable other relationships
            matches = (
                session.scalars(
                    select(DBMatch)
                    .options(
                        joinedload(DBMatch.team1).noload("*"),
                        joinedload(DBMatch.team2).noload("*"),
                        joinedload(DBMatch.season).noload("*"),
                        joinedload(DBMatch.fixed_map),
                    )
                    .where(filter)
                )
                .unique()
                .all()
                if filter is not None
                else []
            )
            if not matches:
                logger.debug(f"No matches found by searchcriteria: {query}")
                return result
            for match in matches:
                result.append(Match.from_dbmatch(match))
            return result

    def create_match(self, match: Match) -> Match:
        return self.add(match)

    def update_match(self, match_id: int, match: Match) -> Match:
        return self.update(match_id, match)

    def delete_match(self, match_id: int) -> None:
        self.delete(match_id)

    def get_match(self, match_id: int) -> Match:
        match_data = self.get(match_id)
        if not match_data:
            raise NotFoundException(f"Match not found by Id: {match_id}")
        return match_data
