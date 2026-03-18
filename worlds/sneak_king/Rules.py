import typing

from rule_builder.rules import Rule, Has
from worlds.generic.Rules import forbid_item
from .Locations import all_locations

if typing.TYPE_CHECKING:
    from . import SneakKingWorld

mission_rules: dict[str, "Rule[SneakKingWorld]"] = {}

for location in all_locations:
    level = location.name.split(': Mission ')[0]
    mission_num = int(location.name.split('Mission ')[1].split(' Rank')[0])

    if mission_num != 1:
        item_name = f"{level} Mission {mission_num} Unlock"
        mission_rules[location.name] = Has(item_name)

def set_rules(world: "SneakKingWorld"):
    from .Regions import region_names

    # Set mission unlock rules
    for location_name, rule in mission_rules.items():
        world.set_rule(world.get_location(location_name), rule)

    # Prevent region unlock items from being placed in their own region
    starting_region = region_names[world.options.starting_level.value]
    for region_name in region_names:
        if region_name == starting_region:
            continue  # Starting region unlock doesn't exist in item pool

        region_unlock_item = f"{region_name} Unlock"
        region = world.multiworld.get_region(region_name, world.player)
        for location in region.locations:
            forbid_item(location, region_unlock_item, world.player)