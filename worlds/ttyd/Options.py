from Options import Range, StartInventoryPool, PerGameCommonOptions, Choice, FreeText, TextChoice, Toggle
from dataclasses import dataclass


class ChapterClears(Range):
    """
    This determines how many chapter clears are required to enter the Palace of Shadow.
    """
    display_name = "Required Chapter Clears"
    range_start = 0
    range_end = 7
    default = 7

class PitItems(Choice):
    """
    This determines what type of items are in the Pit of 100 Trials.
    vanilla: The locations contain the same items as the original game, and the locations themselves will not be created.
    filler: The locations contain random filler items.
    all: The locations can contain any item.
    """
    display_name = "Pit Items"
    option_vanilla = 0
    option_filler = 1
    option_all = 2
    default = 1

class LimitChapterLogic(Toggle):
    """
    Progression items will only appear in required chapters, and in common areas. You will not need to
    check the chapters that are out of logic whatsoever. You can still visit them for local items (badges, consumables, etc) if you want or need to.
    """
    display_name = "Limit Chapter Logic"

class LimitChapterEight(Toggle):
    """
    All chapter 8 keys items will be placed in vanilla locations.
    All other locations will have local non-progression items.
    """
    display_name = "Limit Chapter 8"

class PalaceSkip(Toggle):
    """
    Entering the Thousand-Year door will take you straight to Grodus.
    """
    display_name = "Palace Skip"

class StartingCoins(Range):
    """
    How many coins you start with.
    """
    display_name = "Starting Coins"
    range_start = 0
    range_end = 999
    default = 100

class StartingPartner(Choice):
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
    pit_items: PitItems
    limit_chapter_logic: LimitChapterLogic
    limit_chapter_eight: LimitChapterEight
    palace_skip: PalaceSkip
    starting_coins: StartingCoins
    starting_partner: StartingPartner
    yoshi_color: YoshiColor
    yoshi_name: YoshiName
