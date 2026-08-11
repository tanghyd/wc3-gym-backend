from src.schemas.base import APISchema


class Map(APISchema):
    id: int | None = None
    name: str | None = None
    shortname: str | None = None
    image: str | None = None

    @classmethod
    def from_dbmap(cls, map):
        return cls(
            id=map.id,
            name=map.name,
            shortname=map.shortname,
            image=map.image,
        )

    @staticmethod
    def schema():
        return {
            'type': 'object',
            'properties': {
                'name': {'type': 'string'},
                'shortname': {'type': 'string'},
                'image': {'type': 'string'}

            },
            'required': ['name', 'shortname']
        }
