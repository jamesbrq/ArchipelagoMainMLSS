from Options import Range, StartInventoryPool, PerGameCommonOptions, Choice, FreeText, TextChoice, OptionSet
from dataclasses import dataclass


class ChapterClears(Range):
    """
    This determines how many chapter clears are required to enter the Palace of Shadow.
    """
    display_name = "Required Chapter Clears"
    range_start = 0
    range_end = 7
    default = 7

class StartingCoins(Range):
    """
    How many coins you start with.
    """
    display_name = "Starting Coins"
    range_start = 0
    range_end = 999
    default = 100

class StartingPartner(TextChoice):
    """
    Choose the partner that you start with.
    """
    display_name = "Starting Partner"
    option_goombella = 1
    option_koops = 2
    option_bobbery = 3
    option_yoshi = 4
    option_flurrie = 5
    option_vivian = 6
    option_ms_mowz = 7
    option_random = 8
    default = 1

class YoshiColor(Choice):
    """
    Select the color of your Yoshi partner.
    """
    display_name = "Yoshi Color"
    option_green = 0
    option_red = 1
    option_blue = 2
    option_orange = 3
    option_pink = 4
    option_black = 5
    option_white = 6
    option_random = 7
    default = 0

class YoshiName(FreeText):
    """
    Set the name of your Yoshi partner.
    This has a maximum length of 8 characters.
    """
    display_name = "Yoshi Name"
    default = "Yoshi"



@dataclass
class TTYDOptions(PerGameCommonOptions):
    start_inventory_from_pool: StartInventoryPool
    chapter_clears: ChapterClears
    starting_coins: StartingCoins
    starting_partner: StartingPartner
    yoshi_color: YoshiColor
    yoshi_name: YoshiName
