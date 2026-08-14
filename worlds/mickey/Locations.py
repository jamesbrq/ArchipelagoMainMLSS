from typing import Dict, Final, List

from BaseClasses import Location


class LocationData:
    name: str
    id: int
    region: str
    area: int
    type: str
    offsets: Final[tuple[str, ...]]
    vanilla_item: int | None

    def __init__(self, name: str = "", id: int = 0, region: str = "", area: int = 0, type: str = "", offsets: List[str] | None = None, vanilla_item: int | None = None):
        self.name = name
        self.id = id
        self.region = region
        self.area = area
        self.type = type
        self.offsets = tuple(offsets or ())
        self.vanilla_item = vanilla_item


class MickeyLocation(Location):
    game: str = "Disney's Magical Mirror"


def import_locations() -> List[LocationData]:
    import orjson
    import pkgutil

    return [LocationData(**loc) for loc in orjson.loads(pkgutil.get_data(__name__, "json/locations.json").decode("utf-8"))]


all_locations: List[LocationData] = import_locations()

location_table: Dict[str, int] = {loc.name: loc.id for loc in all_locations}

location_id_to_name: Dict[int, str] = {loc.id: loc.name for loc in all_locations if loc.id is not None}

locationName_to_data: Dict[str, LocationData] = {loc.name: loc for loc in all_locations}


def get_locations_by_type(types: str | List[str]) -> List[LocationData]:
    if isinstance(types, str):
        types = [types]
    return [loc for loc in all_locations if loc.type in types]


def get_locations_by_region(region: str) -> List[LocationData]:
    return [loc for loc in all_locations if loc.region == region]
