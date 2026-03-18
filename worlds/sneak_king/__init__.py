import typing

import settings
from BaseClasses import Tutorial, Item
from worlds.AutoWorld import World, WebWorld
from .Items import items, SneakKingItem, item_table
from .Locations import all_locations
from .Options import SneakKingOptions
from .Regions import create_regions, connect_regions
from .Rules import set_rules


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
    class RomFile(settings.UserFilePath):
        """File name of the MLSS US rom"""

        copy_to = "Sneak King.iso"
        description = "Sneak King ROM File"

    rom_file: RomFile = RomFile(RomFile.copy_to)
    rom_start: bool = False

class SneakKingWorld(World):
    game = "Sneak King"
    web = SneakKingWebWorld()
    options_dataclass = SneakKingOptions
    options = SneakKingOptions
    settings = typing.ClassVar[SneakKingSettings]
    location_name_to_id = {location.name: location.id for location in all_locations}
    item_name_to_id = {item.name: item.id for item in items}

    disabled_regions: set[str]
    disabled_locations: set[str]

    def generate_early(self):
        self.disabled_regions = set()
        self.disabled_locations = set()


    def create_regions(self) -> None:
        create_regions(self)
        connect_regions(self)


    def set_rules(self) -> None:
        from rule_builder.rules import And, Has
        from .Regions import region_names
        set_rules(self)

        # Victory requires having all mission unlock items (missions 2-20 for all 4 levels = 76 items)
        mission_unlock_rules = []
        for level in region_names:
            for mission_num in range(2, 21):
                mission_unlock_rules.append(Has(f"{level} Mission {mission_num} Unlock"))

        self.set_completion_rule(And(*mission_unlock_rules))


    def create_items(self):
        from .Regions import region_names
        starting_region = region_names[self.options.starting_level.value]
        starting_region_unlock = f"{starting_region} Unlock"

        # Create items, excluding the starting region's unlock item
        _items = []
        for item in items:
            if item.name == starting_region_unlock:
                continue  # Skip the starting region's unlock - it's not needed
            _items += [self.create_item(item.name) for _ in range(item.frequency)]

        unfilled = len(self.multiworld.get_unfilled_locations(self.player)) - len(_items)
        _items += [self.create_item("Nothing") for _ in range(unfilled)]
        self.multiworld.itempool += _items


    def create_item(self, name: str) -> Item:
        item = item_table[name]
        return SneakKingItem(item.name, item.classification, item.id, self.player)


    def generate_output(self, output_directory: str) -> None:
        return
