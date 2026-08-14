import typing
from collections.abc import Mapping
from types import MappingProxyType
from typing import Dict, Final, List

from BaseClasses import Region

from .Locations import LocationData, MickeyLocation, all_locations

if typing.TYPE_CHECKING:
    from . import MickeyWorld


class EntranceData:
    """One region-to-region connection, from json/entrances.json.

    Names are unique by construction: area006 and area027 have parallel edges, so
    a bare "A -> B" would collide and one edge's access rule would silently
    overwrite the other's. Duplicates get a "#n" suffix, assigned by
    tools/gen_ap_rules.py, which also keys the entrance rules -- so the two files
    always agree.

    NOT every warp in the game appears here. Excluded:
      * 93 `omake` edges. They all originate from area050, the Bonus Room, whose
        TV re-watches cutscenes -- the player is warped in so a script can play,
        not given access. Structural proof: a normal room reaches its neighbours
        through the warp table at ADB+0x18 and has NO direct Warp_set call
        (area026 has zero); area050 has exactly one, fanning out to 36 areas via
        a runtime table lookup.
      * 12 negated requirements. "Before flag X is set" cannot be expressed --
        CollectionState only grows.
      * runtime-computed destinations and self-loops.
    """

    name: str
    frm: str
    to: str

    def __init__(self, name: str, frm: str, to: str):
        self.name = name
        self.frm = frm
        self.to = to


class RegionData:
    name: str
    areas: Final[tuple[int, ...]]
    locations: Final[tuple[int, ...]]

    def __init__(self, name: str, areas: List[int] | None = None, locations: List[int] | None = None):
        self.name = name
        self.areas = tuple(areas or ())
        self.locations = tuple(locations or ())


def import_entrances() -> tuple[EntranceData, ...]:
    import orjson
    import pkgutil

    return tuple(EntranceData(**e) for e in orjson.loads(pkgutil.get_data(__name__, "json/entrances.json").decode("utf-8")))


def import_regions() -> Mapping[str, RegionData]:
    import orjson
    import pkgutil

    raw = orjson.loads(pkgutil.get_data(__name__, "json/regions.json").decode("utf-8"))
    return MappingProxyType({name: RegionData(name, **data) for name, data in raw.items()})


region_table: Final[Mapping[str, RegionData]] = import_regions()

all_entrances: Final[tuple[EntranceData, ...]] = import_entrances()

region_names: Final[tuple[str, ...]] = tuple(region_table)

locations_by_region: Final[Mapping[str, tuple[LocationData, ...]]] = MappingProxyType({
    name: tuple(loc for loc in all_locations if loc.region == name)
    for name in region_table
})


def create_regions(world: "MickeyWorld") -> None:
    """Create the Menu region plus one region per room, and attach its checks."""
    multiworld = world.multiworld
    player = world.player

    menu = Region("Menu", player, multiworld)
    multiworld.regions.append(menu)

    created: Dict[str, Region] = {"Menu": menu}
    for name in region_names:
        region = Region(name, player, multiworld)
        for loc in locations_by_region[name]:
            if loc.name in world.disabled_locations:
                continue
            region.locations.append(MickeyLocation(player, loc.name, loc.id, region))
        multiworld.regions.append(region)
        created[name] = region

    world.created_regions = created


def connect_regions(world: "MickeyWorld") -> None:
    """Wire the region graph, and connect Menu to the starting region.

    Regions that hold no checks still need to exist, because they can sit on the
    path between two that do -- a hallway with nothing in it is still a hallway.
    They are created here on demand rather than in create_regions, which only
    knows about regions from the location table.
    """
    multiworld = world.multiworld
    player = world.player
    created = world.created_regions

    def region(name: str) -> Region:
        if name not in created:
            made = Region(name, player, multiworld)
            multiworld.regions.append(made)
            created[name] = made
        return created[name]

    for entrance in all_entrances:
        region(entrance.frm).connect(region(entrance.to), entrance.name)

    # The start region. data/ap_rules.json and data/map.json disagree here --
    # area008 versus area012 entrance 14 -- and that is unresolved (#41). area008
    # is used because it is what the solver proves completability from; if it is
    # wrong, every reachability result checked against it is wrong too, so this
    # is the one line to revisit first if generation behaves oddly.
    #
    # NOT world.origin_region_name: that is Archipelago's reachability root, and
    # it stays "Menu". Pointing it at area008 would leave Menu an orphan that
    # nothing sweeps through, and the edge below dead.
    start = world.start_region_name
    region(start)
    created["Menu"].connect(created[start], "Start")
