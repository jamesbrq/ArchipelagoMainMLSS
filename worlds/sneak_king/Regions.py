import typing

from BaseClasses import Region
from rule_builder.rules import Has
from .Locations import get_locations_by_tag, LocationData, SneakKingLocation
from .Options import LevelUnlockMethod

if typing.TYPE_CHECKING:
    from . import SneakKingWorld

region_names = ["Sawmill", "Cul-De-Sac", "Construction", "Downtown"]

def create_regions(world: "SneakKingWorld"):
    # Create menu region (always included)
    menu_region = Region("Menu", world.player, world.multiworld)
    world.multiworld.regions.append(menu_region)

    # Create other regions from dictionary, excluding any in disabled_regions
    regions_dict = get_regions_dict()
    for name, locations in regions_dict.items():
        if name not in world.disabled_regions:
            create_region(world, name, locations)
        else:
            world.disabled_locations.update([loc.name for loc in locations if loc.name not in world.disabled_locations])


def create_region(world: "SneakKingWorld", name: str, locations: list[LocationData]):
    """Create a region with the given name and locations."""
    reg = Region(name, world.player, world.multiworld)
    reg.add_locations({loc.name: loc.id for loc in locations if loc.name not in world.disabled_locations}, SneakKingLocation)
    world.multiworld.regions.append(reg)


def connect_regions(world: "SneakKingWorld"):
    connections_dict = get_region_connections_dict(world)
    names: typing.Dict[str, int] = {}

    # Connect regions based on the connections dictionary, excluding any with excluded regions
    for (source, target), rule in connections_dict.items():
        # Skip connections where either the source or target is in excluded_regions
        if source in world.disabled_regions or target in world.disabled_regions:
            continue

        # Verify that both regions exist before trying to connect them
        try:
            world.multiworld.get_region(source, world.player)
            world.multiworld.get_region(target, world.player)
            connect(world, names, source, target, rule)
        except Exception:
            continue


def get_regions_dict():
    return {
        "Sawmill": get_locations_by_tag("Sawmill"),
        "Cul-De-Sac": get_locations_by_tag("Cul-De-Sac"),
        "Construction": get_locations_by_tag("Construction"),
        "Downtown": get_locations_by_tag("Downtown")
    }


def get_level_order(world: "SneakKingWorld") -> list[str]:
    """Get the ordered list of levels. Starting level is always first.
    If level_shuffle is enabled, the remaining levels are shuffled."""
    starting_region = region_names[world.options.starting_level.value]
    other_regions = [r for r in region_names if r != starting_region]

    if world.options.level_shuffle:
        world.random.shuffle(other_regions)

    return [starting_region] + other_regions


def get_region_connections_dict(world: "SneakKingWorld"):
    level_order = world.level_order
    connections = {
        ("Menu", level_order[0]): None,  # Starting region is always accessible
    }

    if world.options.level_unlock_method == LevelUnlockMethod.option_unlock_item:
        # All non-starting regions connect from Menu with their unlock item
        for region in level_order[1:]:
            connections[("Menu", region)] = Has(f"{region} Unlock")
    else:
        # x_missions: linear chain where completing X missions in region N unlocks region N+1
        # Mission 1 is always available (no unlock needed), so we need X-1 unlock items
        required_unlocks = world.options.level_unlock_range.value - 1
        for i in range(1, len(level_order)):
            prev_region = level_order[i - 1]
            curr_region = level_order[i]
            connections[(prev_region, curr_region)] = Has(
                f"{prev_region}_Missions", required_unlocks
            )

    return connections


def connect(world: "SneakKingWorld",
            used_names: typing.Dict[str, int],
            source: str,
            target: str,
            rule: typing.Optional[typing.Callable] = None):
    """Connect two regions with an optional access rule."""
    source_region = world.multiworld.get_region(source, world.player)
    target_region = world.multiworld.get_region(target, world.player)

    if target not in used_names:
        used_names[target] = 1
        name = target
    else:
        used_names[target] += 1
        name = target + (" " * used_names[target])

    source_region.connect(target_region, name, rule)
