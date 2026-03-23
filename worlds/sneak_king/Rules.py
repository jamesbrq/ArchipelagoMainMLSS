import typing

from rule_builder.rules import Rule, Has
from worlds.generic.Rules import forbid_item
from .Locations import all_locations
from .Regions import region_names
from .Options import LevelUnlockMethod

if typing.TYPE_CHECKING:
    from . import SneakKingWorld

mission_rules: dict[str, "Rule[SneakKingWorld]"] = {}

for location in all_locations:
    if "mission" not in location.tags:
        continue
    level = location.name.split(': Mission ')[0]
    mission_num = int(location.name.split('Mission ')[1].split(' Rank')[0])

    if mission_num != 1:
        item_name = f"{level} Mission {mission_num} Unlock"
        mission_rules[location.name] = Has(item_name)

def set_rules(world: "SneakKingWorld"):
    # Set mission unlock rules
    for location_name, rule in mission_rules.items():
        if location_name not in world.disabled_locations:
            world.set_rule(world.get_location(location_name), rule)

    starting_region = region_names[world.options.starting_level.value]

    if world.options.level_unlock_method == LevelUnlockMethod.option_unlock_item:
        # Prevent region unlock items from being placed in their own region
        for region_name in region_names:
            if region_name == starting_region:
                continue  # Starting region unlock doesn't exist in item pool

            region_unlock_item = f"{region_name} Unlock"
            region = world.multiworld.get_region(region_name, world.player)
            for location in region.locations:
                forbid_item(location, region_unlock_item, world.player)
    else:
        # x_missions chain mode: Region[0] -> Region[1] -> Region[2] -> Region[3]
        # Completing X missions in Region[i] unlocks Region[i+1].
        # Forbid Region[i]'s mission unlocks from regions that come AFTER Region[i+1]
        # in the chain, since those regions can't be reached without first completing
        # Region[i]'s missions. This helps the fill algorithm avoid dead ends.
        level_order = world.level_order
        for i, source_region in enumerate(level_order):
            # Regions after the one this source unlocks
            forbidden_regions = level_order[i + 2:] if i + 2 < len(level_order) else []
            if not forbidden_regions:
                continue

            for mission_num in range(2, 21):
                mission_unlock_item = f"{source_region} Mission {mission_num} Unlock"
                for forbidden_region in forbidden_regions:
                    if forbidden_region not in world.disabled_regions:
                        region = world.multiworld.get_region(forbidden_region, world.player)
                        for location in region.locations:
                            forbid_item(location, mission_unlock_item, world.player)
