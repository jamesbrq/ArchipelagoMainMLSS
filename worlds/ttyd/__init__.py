import os
import pkgutil
import typing
import settings
from BaseClasses import Tutorial, ItemClassification
from worlds.AutoWorld import WebWorld, World
from .Locations import all_locations, location_table
from .Options import TTYDOptions
from .Items import TTYDItem, itemList, item_frequencies, item_table
from .Regions import create_regions, connect_regions
from .Rules import set_rules


class TTYDWebWorld(WebWorld):
    theme = 'partyTime'
    bug_report_page = "https://github.com/jamesbrq/ArchipelagoMLSS/issues"
    tutorials = [
        Tutorial(
            tutorial_name='Setup Guide',
            description='A guide to setting up Paper Mario; The Thousand Year Door for Archipelago.',
            language='English',
            file_name='setup_en.md',
            link='setup/en',
            authors=['jamesbrq']
        )
    ]


class TTYDSettings(settings.Group):
    class RomFile(settings.UserFilePath):
        """File name of the MLSS US rom"""
        copy_to = "Paper Mario - The Thousand Year Door"
        description = "TTYD ROM File"
        md5s = ["4b1a5897d89d9e74ec7f630eefdfd435"]

    rom_file: RomFile = RomFile(RomFile.copy_to)
    rom_start: bool = True


class MLSSWorld(World):
    """
    TTYD
    """
    game = "Paper Mario The Thousand Year Door"
    web = TTYDWebWorld()
    data_version = 1
    options_dataclass = TTYDOptions
    options: TTYDOptions
    settings: typing.ClassVar[TTYDSettings]
    item_name_to_id = {name: data.code for name, data in item_table.items()}
    location_name_to_id = {loc_data.name: loc_data.id for loc_data in all_locations}
    required_client_version = (0, 4, 5)

    excluded_locations = []

    def create_regions(self) -> None:
        create_regions(self, self.excluded_locations)
        connect_regions(self)

    def generate_basic(self) -> None:
        print("Pog")

    def create_items(self) -> None:
        # First add in all progression and useful items
        required_items = []
        precollected = [item for item in itemList if item in self.multiworld.precollected_items]
        for item in itemList:
            if item not in precollected:
                if item.progression == ItemClassification.progression or item.progression == ItemClassification.useful:
                    freq = item_frequencies.get(item.itemName, 1)
                    required_items += [item.itemName for _ in range(freq)]
        for itemName in required_items:
            self.multiworld.itempool.append(self.create_item(itemName))

        # Then, get a random amount of fillers until we have as many items as we have locations
        filler_items = []
        for item in itemList:
            if item.progression == ItemClassification.filler:
                freq = item_frequencies.get(item.itemName)
                if freq is None:
                    freq = 1
                filler_items += [item.itemName for _ in range(freq)]

        remaining = len(all_locations) - len(required_items)
        for i in range(remaining):
            filler_item_name = self.multiworld.random.choice(filler_items)
            item = self.create_item(filler_item_name)
            self.multiworld.itempool.append(item)
            filler_items.remove(filler_item_name)

    def set_rules(self) -> None:
        set_rules(self, self.excluded_locations)
        self.multiworld.completion_condition[self.player] = \
            lambda state: state.can_reach("Palace of Shadow", "Region", self.player)

    def create_item(self, name: str) -> TTYDItem:
        item = item_table[name]
        return TTYDItem(item.itemName, item.progression, item.code, self.player)
