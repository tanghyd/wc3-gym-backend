import logging

from app.exceptions import DBException, NotFoundException
from app.models.map import DBMap
from app.schemas.map import Map
from app.services.base import BaseService
from app.utils.query_util import QueryElement, QueryUtil

logger = logging.getLogger(__name__)


class MapService(BaseService):
    def add(self, map: Map) -> Map:
        with self.get_session() as session:
            db_map = DBMap.add(session, map.to_dict())
            if not db_map:
                raise DBException("Map could not be created!")
            return Map.from_dbmap(db_map)

    def update(self, map: Map) -> Map:
        with self.get_session() as session:
            db_map = DBMap.update(session, map.id, **map.to_dict())
            if not db_map:
                raise DBException("Map could not be updated")
            return Map.from_dbmap(db_map)

    def delete(self, map_id: int) -> None:
        with self.get_session() as session:
            DBMap.delete(session, map_id)

    def get(self, map_id: int) -> Map | None:
        with self.get_session() as session:
            map = DBMap.getById(session, map_id)
            if not map:
                return None
            return Map.from_dbmap(map)

    def search(self, query: QueryElement | None) -> list[Map]:
        with self.get_session() as session:
            result: list[Map] = []
            filter = QueryUtil.convertQueryToDBFilter(DBMap, query)
            maps = DBMap.search(session, filter)
            if not maps:
                logger.debug(f"No maps found by searchcriteria: {query}")
                return result

            for map in maps:
                result.append(Map.from_dbmap(map))
            return result

    def getAll(self) -> list[Map]:
        with self.get_session() as session:
            result: list[Map] = []
            maps = DBMap.getAll(session)

            for map in maps:
                result.append(Map.from_dbmap(map))
            return result

    def create_map(self, map: Map) -> Map:
        # remove id, db generates the id
        map.id = None
        return self.add(map)

    def update_map(self, map_id: int, map: Map) -> Map:
        map.id = map_id
        return self.update(map)

    def delete_map(self, map_id: int) -> None:
        self.delete(map_id)

    def get_map(self, map_id: int) -> Map:
        map_data = self.get(map_id)
        if not map_data:
            raise NotFoundException(f"Map not found by Id: {map_id}")
        return map_data
