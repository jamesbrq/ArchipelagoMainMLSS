import os
import typing
import settings
from BaseClasses import Tutorial, ItemClassification
from worlds.AutoWorld import WebWorld, World
from .Locations import all_locations, location_table
from .Options import TTYDOptions
from .Items import TTYDItem, itemList, item_frequencies, item_table
from .Regions import create_regions, connect_regions
from .Rom import TTYDProcedurePatch, write_files
from .Rules import set_rules
from worlds.LauncherComponents import Component, SuffixIdentifier, Type, components, launch_subprocess

def launch_client(*args):
    from .TTYDClient import launch
    launch_subprocess(launch, name="TTYDClient", args=args)


components.append(
    Component(
        "TTYDClient",
        func=launch_client,
        component_type=Type.CLIENT,
        file_identifier=SuffixIdentifier(".apttyd"),
    ),
)


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
        """File name of the TTYD US iso"""
        copy_to = "Paper Mario - The Thousand Year Door.iso"
        description = "TTYD GC .iso File"

    rom_file: RomFile = RomFile(RomFile.copy_to)
    rom_start: bool = True


class TTYDWorld(World):
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
        item = self.create_item("Diamond Star")
        self.multiworld.get_location("Hooktail's Castle Hooktail's Room: Diamond Star", self.player).place_locked_item(item)
        item = self.create_item("Emerald Star")
        self.multiworld.get_location("Great Tree Entrance: Emerald Star", self.player).place_locked_item(item)
        item = self.create_item("Gold Star")
        self.multiworld.get_location("Glitzville Arena: Gold Star", self.player).place_locked_item(item)
        item = self.create_item("Ruby Star")
        self.multiworld.get_location("Creepy Steeple Upper Room: Ruby Star", self.player).place_locked_item(item)
        item = self.create_item("Sapphire Star")
        self.multiworld.get_location("Pirate's Grotto Cortez' Hoard: Sapphire Star", self.player).place_locked_item(item)
        item = self.create_item("Garnet Star")
        self.multiworld.get_location("Poshley Heights Sanctum Altar: Garnet Star", self.player).place_locked_item(item)
        item = self.create_item("Crystal Star")
        self.multiworld.get_location("X-Naut Fortress Boss Room: Crystal Star", self.player).place_locked_item(item)

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

        remaining = len(all_locations) - len(required_items) - 7
        for i in range(remaining):
            filler_item_name = self.multiworld.random.choice(filler_items)
            item = self.create_item(filler_item_name)
            self.multiworld.itempool.append(item)
            filler_items.remove(filler_item_name)

    def set_rules(self) -> None:
        set_rules(self, self.excluded_locations)
        self.multiworld.completion_condition[self.player] = \
            lambda state: state.can_reach("Palace of Shadow Final Staircase: Ultra Shroom", "Location", self.player)

    def create_item(self, name: str) -> TTYDItem:
        item = item_table[name]
        return TTYDItem(item.itemName, item.progression, item.code, self.player)

    def generate_output(self, output_directory: str) -> None:
        patch = TTYDProcedurePatch(player=self.player, player_name=self.multiworld.player_name[self.player])
        write_files(self, patch)
        rom_path = os.path.join(
            output_directory, f"{self.multiworld.get_out_file_name_base(self.player)}" f"{patch.patch_file_ending}"
        )
        patch.write(rom_path)
