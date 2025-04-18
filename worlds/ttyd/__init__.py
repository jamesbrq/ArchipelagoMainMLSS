import os
import typing
from settings import UserFilePath, Group
from BaseClasses import Tutorial, ItemClassification, CollectionState, Item
from Utils import visualize_regions
from worlds.AutoWorld import WebWorld, World
from .Data import starting_partners
from .Locations import all_locations, location_table, pit
from .Options import TTYDOptions, YoshiColor, StartingPartner
from .Items import TTYDItem, itemList, item_frequencies, item_table, ItemData
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


class TTYDSettings(Group):
    class DolphinPath(UserFilePath):
        """
        The location of the Dolphin you want to auto launch patched ROMs with
        """
        is_exe = True
        description = "Dolphin Executable"

    class RomFile(UserFilePath):
        """File name of the TTYD US iso"""
        copy_to = "Paper Mario - The Thousand Year Door.iso"
        description = "US TTYD .iso File"

    dolphin_path: DolphinPath = DolphinPath(None)
    rom_file: RomFile = RomFile(RomFile.copy_to)
    rom_start: bool = True


class TTYDWorld(World):
    """
    TTYD
    """
    game = "Paper Mario The Thousand Year Door"
    web = TTYDWebWorld()

    options_dataclass = TTYDOptions
    options: TTYDOptions
    settings: typing.ClassVar[TTYDSettings]
    item_name_to_id = {name: data.code for name, data in item_table.items()}
    location_name_to_id = {loc_data.name: loc_data.id for loc_data in all_locations}
    required_client_version = (0, 6, 0)
    disabled_locations: set

    def generate_early(self) -> None:
        self.disabled_locations = set()
        if self.options.exclude_pit:
            self.disabled_locations.update(location.name for location in pit if "Pit of 100 Trials" in location.name)
        if self.options.yoshi_color.value == YoshiColor.option_random:
            self.options.yoshi_color.value = self.multiworld.random.randint(0, 6)
        if self.options.starting_partner.value == StartingPartner.option_random:
            self.options.starting_partner.value = self.multiworld.random.randint(1, 7)

    def create_regions(self) -> None:
        create_regions(self)
        connect_regions(self)
        self.lock_item("Rogueport Center: Goombella", starting_partners[self.options.starting_partner.value - 1])
        self.lock_item("Hooktail's Castle Hooktail's Room: Diamond Star", "Diamond Star")
        self.lock_item("Great Tree Entrance: Emerald Star", "Emerald Star")
        self.lock_item("Glitzville Arena: Gold Star", "Gold Star")
        self.lock_item("Creepy Steeple Upper Room: Ruby Star", "Ruby Star")
        self.lock_item("Pirate's Grotto Cortez' Hoard: Sapphire Star", "Sapphire Star")
        self.lock_item("Poshley Heights Sanctum Altar: Garnet Star", "Garnet Star")
        self.lock_item("X-Naut Fortress Boss Room: Crystal Star", "Crystal Star")
        self.lock_item("Shadow Queen", "Victory")

    def create_items(self) -> None:
        # First add in all progression and useful items
        required_items = []
        precollected = [item for item in itemList if item in self.multiworld.precollected_items]
        for item in [item for item in itemList if item.progression == ItemClassification.progression or item.progression == ItemClassification.useful]:
            if item not in precollected and item.itemName != starting_partners[self.options.starting_partner.value - 1]:
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

        remaining = len(all_locations) - len(required_items) - len(self.disabled_locations) - 9
        for i in range(remaining):
            filler_item_name = self.multiworld.random.choice(filler_items)
            item = self.create_item(filler_item_name)
            self.multiworld.itempool.append(item)
            filler_items.remove(filler_item_name)

    def set_rules(self) -> None:
        set_rules(self)
        self.multiworld.completion_condition[self.player] = lambda state: state.has("Victory", self.player)

    def create_item(self, name: str) -> TTYDItem:
        item = item_table.get(name, ItemData(None, name, ItemClassification.progression))
        return TTYDItem(item.itemName, item.progression, item.code, self.player)

    def lock_item(self, location: str, item_name: str):
        item = self.create_item(item_name)
        self.get_location(location).place_locked_item(item)

    def collect(self, state: "CollectionState", item: "Item") -> bool:
        change = super().collect(state, item)
        if change and item.name in ["Crystal Star", "Garnet Star", "Sapphire Star", "Ruby Star", "Gold Star", "Emerald Star", "Diamond Star"]:
            state.prog_items[item.player]["stars"] += 1
        return change

    def remove(self, state: "CollectionState", item: "Item") -> bool:
        change = super().remove(state, item)
        if change and item.name in ["Crystal Star", "Garnet Star", "Sapphire Star", "Ruby Star", "Gold Star", "Emerald Star", "Diamond Star"]:
            state.prog_items[item.player]["stars"] -= 1
        return change

    def generate_output(self, output_directory: str) -> None:
        patch = TTYDProcedurePatch(player=self.player, player_name=self.multiworld.player_name[self.player])
        write_files(self, patch)
        rom_path = os.path.join(
            output_directory, f"{self.multiworld.get_out_file_name_base(self.player)}" f"{patch.patch_file_ending}"
        )
        patch.write(rom_path)
