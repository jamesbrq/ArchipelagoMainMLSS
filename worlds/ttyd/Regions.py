import json
import pkgutil
import typing

from BaseClasses import Entrance, Region
from .Locations import (TTYDLocation, shadow_queen, LocationData)
from . import StateLogic, get_locations_by_tags
from .Rules import _build_single_lambda, get_rule_region_dependencies

if typing.TYPE_CHECKING:
    from . import TTYDWorld
    from entrance_rando import ERPlacementState


# Entrance randomization groups
GROUP_TWO_WAY = 1
GROUP_ONE_WAY = 2
GROUP_DUNGEON_DOOR = 3       # dungeon-side door of a dungeon entrance pair
GROUP_DUNGEON_OVERWORLD = 4  # overworld-side door of a dungeon entrance pair

CHAPTER_TAGS = {1: "One", 2: "Two", 3: "Three", 4: "Four",
                5: "Five", 6: "Six", 7: "Seven", 8: "Eight"}


class TTYDEntrance(Entrance):
    def can_connect_to(self, other: Entrance, dead_end: bool, er_state: "ERPlacementState") -> bool:
        if not super().can_connect_to(other, dead_end, er_state):
            return False
        # One-way softlock constraint: the attic and the Boo-chest background
        # are escapable only through their one-way warp, so a warp from either
        # trap room must not land in a trap room (covers the 2-cycle between
        # them and self-landings). Self-landings elsewhere are harmless -
        # vanilla has one (Palace Torch Stairs Room).
        if other.name.endswith(" Landing"):
            trap_rooms = {"steeple_boo_background", "glitzville_attic"}
            src_tag = load_zones()[self.name].get("src_region")
            dst_tag = load_zones()[other.name.removesuffix(" Landing")]["region"]
            if src_tag in trap_rooms and dst_tag in trap_rooms:
                return False
        return True


class TTYDRegion(Region):
    entrance_type = TTYDEntrance


_regions_cache: typing.Optional[list[dict]] = None
_zones_cache: typing.Optional[dict[str, dict]] = None


def load_regions() -> list[dict]:
    global _regions_cache
    if _regions_cache is None:
        _regions_cache = json.loads(pkgutil.get_data(__name__, "json/regions.json").decode("utf-8"))
    return _regions_cache


def load_zones() -> dict[str, dict]:
    """All loading zones from zones.json, keyed by zone name."""
    global _zones_cache
    if _zones_cache is None:
        zones = json.loads(pkgutil.get_data(__name__, "json/zones.json").decode("utf-8"))
        _zones_cache = {zone["name"]: zone for zone in zones}
    return _zones_cache


def region_name_by_tag() -> dict[str, str]:
    return {region["tag"]: region["name"] for region in load_regions()}


def get_regions_dict() -> dict[str, list[LocationData]]:
    """
    Returns a dictionary mapping region names to their corresponding location data lists.
    """
    regions = {region["name"]: get_locations_by_tags(region["tag"]) for region in load_regions()}
    regions["Shadow Queen"] = shadow_queen
    return regions


def location_region_lookup() -> dict[str, str]:
    """Maps every location name to the name of the region containing it."""
    lookup = {}
    for region_name, locations in get_regions_dict().items():
        for location in locations:
            lookup[location.name] = region_name
    return lookup


# The four blue warp pipes (and their chapter-side counterparts) only function
# while the blue switches exist, i.e. while blue_pipe_toggle is enabled.
BLUE_PIPE_ZONES = {
    "Rogueport Sewers East Warp Room - CH One Warp",
    "Rogueport Sewers East Warp Room - CH Two Warp",
    "Rogueport Sewers West Warp Room - CH Five Warp",
    "Rogueport Sewers West Warp Room - CH Six Warp",
    "Petalburg Eastside - Warp Pipe",
    "Boggly Woods Outside Great Tree - Pipe",
    "Keelhaul Key Jungle Entrance - Pipe",
    "Poshley Heights Sanctum Exterior - Pipe",
}


def get_static_connections(world: "TTYDWorld") -> dict[tuple[str, str], typing.Optional[dict]]:
    """
    Hard-coded in-map traversal edges (not loading zones), as JSON rule dicts.
    None means always traversable. These are never entrance-randomized.
    """
    connections: dict[tuple[str, str], typing.Optional[dict]] = {
        # --- Menu / top-level ---
        ("Menu", "Rogueport Center"): None,
        ("Menu", "Tattlesanity"): None,

        # --- Rogueport West ---
        ("Rogueport West Tall Pipe", "Rogueport West"): None,

        # --- Rogueport Sewers East ---
        ("Rogueport Sewers East", "Rogueport Sewers East Bobbery Pipe"): {"has": "Bobbery"},
        ("Rogueport Sewers East Bobbery Pipe", "Rogueport Sewers East"): {"has": "Bobbery"},
        ("Rogueport Sewers East", "Rogueport Sewers East Fortune Pipe"): {"has": "Paper Mode"},
        ("Rogueport Sewers East Fortune Pipe", "Rogueport Sewers East"): None,
        ("Rogueport Sewers East", "Rogueport Sewers East Plane Mode"): {"has": "Plane Mode"},
        ("Rogueport Sewers East Plane Mode", "Rogueport Sewers East"): None,
        ("Rogueport Sewers East Top", "Rogueport Sewers East"): None,
        ("Rogueport Sewers East Top", "Rogueport Sewers East Fortune Pipe"): {"has": "Yoshi"},
        ("Rogueport Sewers East Top", "Rogueport Sewers East Plane Mode"): None,

        # --- Rogueport Sewers Blooper ---
        ("Rogueport Sewers Blooper", "Rogueport Sewers Blooper Pipe"): None,

        # --- Rogueport Sewers Town ---
        # Fallen pipe: Bobbery, or Paper Mode + Tube Mode
        ("Rogueport Sewers Town", "Rogueport Sewers Town Dazzle"):
            {"or": [{"has": "Bobbery"}, {"function": "tube_curse"}]},
        ("Rogueport Sewers Town Dazzle", "Rogueport Sewers Town"):
            {"or": [{"has": "Bobbery"}, {"function": "tube_curse"}]},
        ("Rogueport Sewers Town Teleporter", "Rogueport Sewers Town"): None,
        ("Rogueport Sewers Town", "Rogueport Sewers Town Teleporter"): None,

        # --- Rogueport Sewers West ---
        ("Rogueport Sewers West", "Rogueport Sewers West West"): {"has": "Yoshi"},
        ("Rogueport Sewers West West", "Rogueport Sewers West"): {"has": "Yoshi"},
        ("Rogueport Sewers West", "Rogueport Sewers West Bottom"): None,
        ("Rogueport Sewers West West", "Rogueport Sewers West Bottom"): None,
        ("Rogueport Sewers West Bottom", "Rogueport Sewers West West"): {"function": "ultra_boots"},
        ("Rogueport Sewers West West", "Rogueport Sewers West Fahr"): {"function": "ultra_hammer"},
        ("Rogueport Sewers West Fahr", "Rogueport Sewers West West"): {"function": "ultra_hammer"},

        # --- Rogueport Sewers Enemy Halls ---
        ("Rogueport Sewers East Enemy Hall", "Rogueport Sewers East Enemy Hall Barred Door"): {"has": "Paper Mode"},
        ("Rogueport Sewers East Enemy Hall Barred Door", "Rogueport Sewers East Enemy Hall"): {"has": "Paper Mode"},
        ("Rogueport Sewers West Enemy Hall", "Rogueport Sewers West Enemy Hall Flurrie"): {"has": "Flurrie"},
        ("Rogueport Sewers West Enemy Hall Flurrie", "Rogueport Sewers West Enemy Hall"): {"has": "Flurrie"},

        # --- Rogueport Sewers Warp Rooms ---
        # Ultra Hammer breaks the blocks between left/right/top; top always drops down
        ("Rogueport Sewers West Warp Room Left", "Rogueport Sewers West Warp Room Right"): {"function": "ultra_hammer"},
        ("Rogueport Sewers West Warp Room Right", "Rogueport Sewers West Warp Room Left"): {"function": "ultra_hammer"},
        ("Rogueport Sewers West Warp Room Left", "Rogueport Sewers West Warp Room Top"): {"function": "ultra_hammer"},
        ("Rogueport Sewers West Warp Room Top", "Rogueport Sewers West Warp Room Left"): None,
        ("Rogueport Sewers West Warp Room Right", "Rogueport Sewers West Warp Room Top"): {"function": "ultra_hammer"},
        ("Rogueport Sewers West Warp Room Top", "Rogueport Sewers West Warp Room Right"): None,
        ("Rogueport Sewers East Warp Room Left", "Rogueport Sewers East Warp Room Right"): {"function": "ultra_hammer"},
        ("Rogueport Sewers East Warp Room Right", "Rogueport Sewers East Warp Room Left"): {"function": "ultra_hammer"},
        ("Rogueport Sewers East Warp Room Left", "Rogueport Sewers East Warp Room Top"): {"function": "ultra_hammer"},
        ("Rogueport Sewers East Warp Room Top", "Rogueport Sewers East Warp Room Left"): None,
        ("Rogueport Sewers East Warp Room Right", "Rogueport Sewers East Warp Room Top"): {"function": "ultra_hammer"},
        ("Rogueport Sewers East Warp Room Top", "Rogueport Sewers East Warp Room Right"): None,

        # --- Rogueport Black Key Room ---
        ("Rogueport Sewers Black Key Room", "Rogueport Sewers Black Key Room Puni Door"): {"has": "Paper Mode"},
        ("Rogueport Sewers Black Key Room Puni Door", "Rogueport Sewers Black Key Room"): {"has": "Paper Mode"},

        # --- Rogueport Second Chapter Entrance Room ---
        ("Rogueport Sewers Puni Room", "Rogueport Sewers Puni Room Exit"): None,

        # --- Entering the Pit (Pit not Randomized) ---
        ("Rogueport Sewers Pit Room", "Pit of 100 Trials"): {"function": "pit"},

        # --- Petal Meadows ---
        ("Petal Meadows Bridge West", "Petal Meadows Bridge East"): None,

        # --- Hooktail's Castle ---
        # Drawbridge: Yoshi can cross bottom level eastward; plane glides west from top
        ("Hooktail's Castle Drawbridge East Bottom", "Hooktail's Castle Drawbridge West Bottom"): {"has": "Yoshi"},
        ("Hooktail's Castle Drawbridge West Bottom", "Hooktail's Castle Drawbridge East Bottom"): None,
        ("Hooktail's Castle Drawbridge East Top", "Hooktail's Castle Drawbridge East Bottom"): None,
        ("Hooktail's Castle Drawbridge East Top", "Hooktail's Castle Drawbridge West Bottom"): {"has": "Plane Mode"},
        ("Hooktail's Castle Drawbridge West Top", "Hooktail's Castle Drawbridge West Bottom"): None,
        ("Hooktail's Castle Stair Switch Room Upper Level", "Hooktail's Castle Stair Switch Room"): None,
        # Koops can press the switch from a distance
        ("Hooktail's Castle Life Shroom Room", "Hooktail's Castle Life Shroom Room Upper Level"): {"has": "Koops"},
        ("Hooktail's Castle Life Shroom Room Upper Level", "Hooktail's Castle Life Shroom Room"): None,
        ("Hooktail's Castle Central Staircase Upper Level", "Hooktail's Castle Central Staircase"): None,

        # --- Boggly Woods ---
        ("Boggly Woods Plane Panel Room", "Boggly Woods Plane Panel Room Upper"): {"has": "Plane Mode"},
        ("Boggly Woods Plane Panel Room Upper", "Boggly Woods Plane Panel Room"): None,
        ("Boggly Woods Outside Flurrie's House", "Boggly Woods Outside Flurrie's House Grass Area"): {"has": "Paper Mode"},
        ("Boggly Woods Outside Flurrie's House Grass Area", "Boggly Woods Outside Flurrie's House"): {"has": "Paper Mode"},
        ("Great Tree 100-Puni Pedestal Upper", "Great Tree 100-Puni Pedestal Lower"):
            {"and": [{"function": "key_both"}, {"has": "Puni Orb"},
                     {"can_reach_region": "Great Tree Red/Blue Cages"},
                     {"can_reach_region": "Great Tree Entrance"}]},

        # --- Glitzville ---
        ("Glitzville Promoter's Office Vent", "Glitzville Promoter's Office"): None,

        # --- Creepy Steeple ---
        ("Creepy Steeple Main Hall Upper", "Creepy Steeple Main Hall"): None,
        ("Creepy Steeple Main Hall Upper South", "Creepy Steeple Main Hall"): None,
        ("Creepy Steeple Well Buzzy Room", "Creepy Steeple Well Buzzy Room Vivian"): {"has": "Vivian"},

        # --- Pirate's Grotto ---
        ("Pirate's Grotto Handle Room Canal", "Pirate's Grotto Handle Room"): {"has": "Boat Mode"},
        ("Pirate's Grotto Sluice Gate Upper", "Pirate's Grotto Sluice Gate Upper Canal"): {"has": "Boat Mode"},
        ("Pirate's Grotto Sluice Gate Upper Canal", "Pirate's Grotto Sluice Gate Upper"): {"has": "Boat Mode"},
        ("Pirate's Grotto Sluice Gate Upper Canal", "Pirate's Grotto Sluice Gate Canal"): None,
        ("Pirate's Grotto Toad Boat Room", "Pirate's Grotto Toad Boat Room East"):
            {"and": [{"has": "Boat Mode"}, {"has": "Plane Mode"}]},
        ("Pirate's Grotto Toad Boat Room East", "Pirate's Grotto Toad Boat Room"): {"has": "Boat Mode"},

        # --- Riverside Station ---
        ("Riverside Station Ultra Boots Room Upper", "Riverside Station Ultra Boots Room"):
            {"and": [{"function": "ultra_boots"}, {"has": "Paper Mode"}]},

        # --- Excess Express ---
        # Storage Car West is unlocked only after completing a chain of story prerequisites
        ("Excess Express Storage Car", "Excess Express Storage Car West"):
            {"and": [{"can_reach_region": "Riverside Station Entrance"},
                     {"has": "Elevator Key (Station)"},
                     {"can_reach_region": "Excess Express Middle Passenger Car"},
                     {"can_reach": "Excess Express Middle Passenger Car: Briefcase"},
                     {"can_reach_region": "Excess Express Locomotive"},
                     {"can_reach_region": "Excess Express Back Passenger Car"},
                     {"can_reach_region": "Excess Express Front Passenger Car"}]},
        ("Excess Express Storage Car West", "Excess Express Storage Car"): None,

        # --- X-Naut Fortress elevators ---
        # Elevator Key 1 covers floors G/B1/B2; Elevator Key 2 covers B2/B3/B4
        ("X-Naut Fortress Hall Ground Floor", "X-Naut Fortress Hall Sublevel One"): {"has": "Elevator Key 1"},
        ("X-Naut Fortress Hall Sublevel One", "X-Naut Fortress Hall Ground Floor"): {"has": "Elevator Key 1"},
        ("X-Naut Fortress Hall Ground Floor", "X-Naut Fortress Hall Sublevel Two"): {"has": "Elevator Key 1"},
        ("X-Naut Fortress Hall Sublevel One", "X-Naut Fortress Hall Sublevel Two"): {"has": "Elevator Key 1"},
        ("X-Naut Fortress Hall Sublevel Two", "X-Naut Fortress Hall Sublevel One"): {"has": "Elevator Key 1"},
        ("X-Naut Fortress Hall Sublevel Two", "X-Naut Fortress Hall Sublevel Three"): {"has": "Elevator Key 2"},
        ("X-Naut Fortress Hall Sublevel Three", "X-Naut Fortress Hall Sublevel Two"): {"has": "Elevator Key 2"},
        ("X-Naut Fortress Hall Sublevel Two", "X-Naut Fortress Hall Sublevel Four"): {"has": "Elevator Key 2"},
        ("X-Naut Fortress Hall Sublevel Four", "X-Naut Fortress Hall Sublevel Two"): {"has": "Elevator Key 2"},
        ("X-Naut Fortress Hall Sublevel Three", "X-Naut Fortress Hall Sublevel Four"): {"has": "Elevator Key 2"},
        ("X-Naut Fortress Hall Sublevel Four", "X-Naut Fortress Hall Sublevel Three"): {"has": "Elevator Key 2"},

        # --- Palace of Shadow ---
        # Each Far Hallway has a post Riddle Tower variant
        ("Palace of Shadow Far Hallway One", "Palace of Shadow Far Hallway One Post Riddle Tower"):
            {"function": "riddle_tower"},
        ("Palace of Shadow Far Hallway 2", "Palace of Shadow Far Hallway 2 Post Riddle"): {"function": "riddle_tower"},
        ("Palace of Shadow Far Hallway 3", "Palace of Shadow Far Hallway 3 Post Riddle"): {"function": "riddle_tower"},
        ("Palace of Shadow Far Hallway 4", "Palace of Shadow Far Hallway 4 Post Riddle"): {"function": "riddle_tower"},
        ("Palace of Shadow Far Backroom 2", "Palace of Shadow Far Backroom 2 Top"): {"has": "Bobbery"},
        ("Palace of Shadow Far Backroom 2 Top", "Palace of Shadow Far Backroom 2"): None,
        # Final staircase -> Shadow Queen (standard route)
        ("Palace of Shadow Final Staircase", "Shadow Queen"): {"function": "PalaceAccessGoal"},
    }

    if world.options.open_westside:
        connections[("Menu", "Rogueport West")] = None
    if world.options.palace_skip:
        # Direct TTYD -> Shadow Queen shortcut used when palace_skip is enabled
        connections[("TTYD", "Shadow Queen")] = {"function": "PalaceAccessGoal"}

    return connections


def create_regions(world: "TTYDWorld"):
    # Create menu region (always included)
    menu_region = TTYDRegion("Menu", world.player, world.multiworld)
    world.multiworld.regions.append(menu_region)

    # Create other regions from regions.json, excluding any in excluded_regions
    for name, locations in get_regions_dict().items():
        if name not in world.excluded_regions:
            create_region(world, name, locations)
        else:
            world.disabled_locations.update([loc.name for loc in locations if loc.name not in world.disabled_locations])


def connect_regions(world: "TTYDWorld"):
    zones = load_zones()
    tag_to_region = region_name_by_tag()
    location_regions = location_region_lookup()
    world.entrance_rules = {}
    world.entrance_region_deps = {}

    def connect(source: str, target: str, rule_dict: typing.Optional[dict], name: typing.Optional[str] = None):
        if source in world.excluded_regions or target in world.excluded_regions:
            return
        source_region = world.multiworld.get_region(source, world.player)
        target_region = world.multiworld.get_region(target, world.player)
        rule = _build_single_lambda(rule_dict, world) if rule_dict is not None else None
        entrance = source_region.connect(target_region, name, rule)
        world.entrance_rules[entrance.name] = rule_dict
        deps = get_rule_region_dependencies(rule_dict, location_regions)
        deps -= world.excluded_regions
        if deps:
            world.entrance_region_deps[entrance.name] = deps

    # Static in-map traversal edges
    for (source, target), rule_dict in get_static_connections(world).items():
        connect(source, target, rule_dict)

    # Loading-zone edges (all vanilla-connected in this step; generic ER
    # disconnects and reshuffles a subset later in connect_entrances)
    for zone in zones.values():
        if not world.options.blue_pipe_toggle and zone["name"] in BLUE_PIPE_ZONES:
            continue
        if zone["target"] == "One Way":
            source = tag_to_region[zone["src_region"]]
            target = tag_to_region[zone["region"]]
        else:
            source = tag_to_region[zone["region"]]
            target = tag_to_region[zones[zone["target"]]["region"]]
        connect(source, target, zone["rules"], zone["name"])


def get_shuffled_zone_names(world: "TTYDWorld") -> list[str]:
    """Names of the loading zones entering the entrance-randomization pool.

    Vanilla-tagged zones, zones of limited chapters, disabled blue pipes and
    zones touching excluded (palace-skipped) regions stay vanilla-connected.
    """
    if not world.options.loading_zone_shuffle:
        return []
    zones = load_zones()
    tag_to_region = region_name_by_tag()
    limited_tags = {CHAPTER_TAGS[chapter] for chapter in world.limited_chapters}
    pool = []
    for zone in zones.values():
        if "vanilla" in zone["tags"]:
            continue
        if not world.options.blue_pipe_toggle and zone["name"] in BLUE_PIPE_ZONES:
            continue
        if any(tag in limited_tags for tag in zone["tags"]):
            continue
        regions = {tag_to_region[zone["region"]]}
        if zone["target"] == "One Way":
            regions.add(tag_to_region[zone["src_region"]])
        else:
            regions.add(tag_to_region[zones[zone["target"]]["region"]])
        if regions & world.excluded_regions:
            continue
        pool.append(zone["name"])
    return sorted(pool)


def zone_group(zone: dict, world: "TTYDWorld") -> int:
    if zone["target"] == "One Way":
        return GROUP_ONE_WAY
    if world.options.dungeon_shuffle:
        if "Dungeon Entrance" in zone["tags"]:
            return GROUP_DUNGEON_DOOR
        if "Dungeon Exit" in zone["tags"]:
            return GROUP_DUNGEON_OVERWORLD
    return GROUP_TWO_WAY


def build_warp_table(pairings: list[tuple[str, str]]) -> dict[tuple[str, str], tuple[str, str]]:
    """Convert ER pairings into the mod's warp override table.

    Two-way overrides are keyed by the vanilla destination door's (map, bero):
    the mod redirects the arrival. One-way warps are keyed by the source zone's
    own (map, bero). Coupled pairings contain both directions, so the reverse
    entries come from their own pairing rows.
    """
    zones = load_zones()
    table: dict[tuple[str, str], tuple[str, str]] = {}
    for exit_name, target_name in pairings:
        source = zones[exit_name]
        if target_name.endswith(" Landing"):
            destination = zones[target_name.removesuffix(" Landing")]
            table[(source["map"], source["bero"])] = (destination["map"], destination["bero"])
        else:
            vanilla_destination = zones[source["target"]]
            new_destination = zones[target_name]
            table[(vanilla_destination["map"], vanilla_destination["bero"])] = \
                (new_destination["map"], new_destination["bero"])
    return table


def register_indirect_connections(world: "TTYDWorld"):
    for entrance_name, deps in world.entrance_region_deps.items():
        entrance = world.get_entrance(entrance_name)
        for dep in deps:
            world.multiworld.register_indirect_condition(world.get_region(dep), entrance)


def create_region(world: "TTYDWorld", name: str, locations: list[LocationData]):
    """Create a region with the given name and locations."""
    reg = TTYDRegion(name, world.player, world.multiworld)
    reg.add_locations({loc.name: loc.id for loc in locations if loc.name not in world.disabled_locations}, TTYDLocation)
    world.multiworld.regions.append(reg)
