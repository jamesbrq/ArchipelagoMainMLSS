import logging
import os
import typing
import re

import settings
from BaseClasses import Tutorial, Item, CollectionState
from worlds.AutoWorld import World, WebWorld
from .Items import items, SneakKingItem, item_table
from .Locations import all_locations
from .Options import SneakKingOptions
from .Patcher import SneakKingProcedurePatch, write_files
from .Regions import create_regions, connect_regions, get_level_order
from .Rules import set_rules
from worlds.LauncherComponents import launch, components, Component, Type, SuffixIdentifier


def launch_client(*args):
    from .SneakKingClient import launch as _launch
    launch(_launch, name="SneakKingClient", args=args)


components.append(
    Component(
        "SneakKingClient",
        func=launch_client,
        component_type=Type.CLIENT,
        file_identifier=SuffixIdentifier(".apsk"),
        description="Open the Sneak King client.",
    ),
)


class SneakKingWebWorld(WebWorld):
    theme = "partyTime"
    bug_report_page = "https://github.com/jamesbrq/SneakKingAP/issues"
    setup_en = Tutorial(
            tutorial_name="Setup Guide",
            description="A guide to setting up Sneak King for Archipelago.",
            language="English",
            file_name="setup_en.md",
            link="setup/en",
            authors=["jamesbrq"],
        )

    tutorials = [setup_en]


class SneakKingSettings(settings.Group):
    class XemuPath(settings.UserFilePath):
        """Path to the xemu executable."""
        is_exe = True
        description = "Xemu Executable"


    class RomFile(settings.UserFilePath):
        """File name of the Sneak King rom"""
        copy_to = "Sneak King.iso"
        description = "Sneak King ROM File"

    xemu_path: XemuPath = XemuPath(None)
    rom_file: RomFile = RomFile(RomFile.copy_to)
    rom_start: bool = False

class SneakKingWorld(World):
    game = "Sneak King"
    web = SneakKingWebWorld()
    options_dataclass = SneakKingOptions
    options: SneakKingOptions
    settings: typing.ClassVar[SneakKingSettings]
    required_client_version = (0, 6, 7)
    location_name_to_id = {location.name: location.id for location in all_locations}
    item_name_to_id = {item.name: item.id for item in items}

    disabled_regions: set[str]
    disabled_locations: set[str]
    level_order: list[str]

    def generate_early(self):
        self.disabled_regions = set()
        self.disabled_locations = set()
        self.level_order = get_level_order(self)
        # implementing yaml-less UT support
        if hasattr(self.multiworld, "re_gen_passthrough"):
            if self.game in self.multiworld.re_gen_passthrough:
                slot_data = self.multiworld.re_gen_passthrough[self.game]
                self.options.goal.value = slot_data["goal"]
                self.options.goal_range.value = slot_data["goal_range"]
                self.options.starting_level.value = slot_data["starting_level"]
                self.options.enabled_ranks.value = slot_data["enabled_ranks"]
                self.options.level_unlock_method.value = slot_data["level_unlock_method"]
                self.options.level_unlock_range.value = slot_data["level_unlock_range"]
                self.options.level_shuffle.value = slot_data["level_shuffle"]
                return
        if not len(self.options.enabled_ranks.value):
            logging.warning(f"{self.player_name}'s Enabled ranks is empty. Enabling Rank C for accessability.")
            self.options.enabled_ranks.value = ["C"]
        for rank in ["C", "B", "A"]:
            if rank not in self.options.enabled_ranks.value:
                self.disabled_locations.update([location.name for location in all_locations if f"Rank {rank}" in location.name])


    def create_regions(self) -> None:
        create_regions(self)
        connect_regions(self)


    def set_rules(self) -> None:
        from rule_builder.rules import And, Has
        from .Regions import region_names
        set_rules(self)

        # Victory requires completing level_unlock_range missions in each level.
        # Mission 1 is always available, so we need (range - 1) mission unlock items per level.
        required_unlocks = self.options.level_unlock_range.value - 1
        completion_rules = [
            Has(f"{level}_Missions", required_unlocks) for level in region_names
        ]
        self.set_completion_rule(And(*completion_rules))


    def create_items(self):
        from .Regions import region_names
        from .Options import LevelUnlockMethod

        starting_region = region_names[self.options.starting_level.value]
        starting_region_unlock = f"{starting_region} Unlock"
        using_x_missions = self.options.level_unlock_method == LevelUnlockMethod.option_x_missions
        total_locations = len(self.multiworld.get_unfilled_locations(self.player))

        # Create items, excluding region unlocks based on unlock method
        _items = []
        for item in items:
            # Skip region unlock items based on unlock method
            if item.name.endswith(" Unlock") and item.name.replace(" Unlock", "") in region_names:
                if using_x_missions:
                    # Skip all region unlocks when using x_missions method
                    continue
                elif item.name == starting_region_unlock:
                    # Skip only starting region unlock when using unlock_item method
                    continue

            # Reduce Progressive item frequency if not enough locations
            # This happens when ranks are disabled
            frequency = item.frequency
            if item.name in ["Progressive Flourish", "Progressive Chain"]:
                # Calculate how many progression items we'd have
                mission_unlocks = 76  # 4 regions × 19 missions
                region_unlocks = 0 if using_x_missions else 3  # Skip starting region
                progressive_items = 6  # 3 Flourish + 3 Chain
                total_progression = mission_unlocks + region_unlocks + progressive_items

                # If we have more progression items than locations, reduce progressive items
                if total_progression > total_locations:
                    excess = total_progression - total_locations
                    # Reduce frequency proportionally, but keep at least 1
                    frequency = max(1, frequency - (excess // 2))

            _items += [self.create_item(item.name) for _ in range(frequency)]

        unfilled = len(self.multiworld.get_unfilled_locations(self.player)) - len(_items)
        _items += [self.create_item("Nothing") for _ in range(unfilled)]
        self.multiworld.itempool += _items


    def create_item(self, name: str) -> Item:
        item = item_table[name]
        return SneakKingItem(item.name, item.classification, item.id, self.player)


    def collect(self, state: "CollectionState", item: "Item") -> bool:
        change = super().collect(state, item)
        level_match = re.match(r"(Sawmill|Cul-De-Sac|Construction|Downtown)", item.name)
        if change and level_match and "Mission" in item.name:
            state.prog_items[item.player][f"{level_match.group(1)}_Missions"] += 1
        return change


    def remove(self, state: "CollectionState", item: "Item") -> bool:
        change = super().remove(state, item)
        level_match = re.match(r"(Sawmill|Cul-De-Sac|Construction|Downtown)", item.name)
        if change and level_match and "Mission" in item.name:
            state.prog_items[item.player][f"{level_match.group(1)}_Missions"] -= 1
        return change



    def fill_slot_data(self) -> dict[str, typing.Any]:
        return {
            "goal": self.options.goal.value,
            "goal_range": self.options.goal_range.value,
            "starting_level": self.options.starting_level.value,
            "enabled_ranks": list(self.options.enabled_ranks.value),
            "level_unlock_method": self.options.level_unlock_method.value,
            "level_unlock_range": self.options.level_unlock_range.value,
            "level_shuffle": self.options.level_shuffle.value,
            "level_order": self.level_order,
        }

    def generate_output(self, output_directory: str) -> None:
        patch = SneakKingProcedurePatch(player=self.player, player_name=self.multiworld.player_name[self.player])
        write_files(self, patch)
        rom_path = os.path.join(
            output_directory, f"{self.multiworld.get_out_file_name_base(self.player)}" f"{patch.patch_file_ending}"
        )
        patch.write(rom_path)
