import typing

import settings
from BaseClasses import Tutorial
from worlds.AutoWorld import World, WebWorld
from .Locations import all_locations
from .Options import SneakKingOptions


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
