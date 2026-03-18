from dataclasses import dataclass

from Options import PerGameCommonOptions, StartInventoryPool, DeathLink, Choice, OptionSet, Toggle, Range, TextChoice
from worlds.shapez.common.options import FloatRangeText


class StartingLevel(Choice):
    display_name = "Starting Level"
    option_sawmill = 0
    option_cul_de_sac = 1
    option_construction = 2
    option_downtown = 3
    default = 0


class EnabledRanks(OptionSet):
    display_name = "Enabled Ranks"
    valid_keys = ["C", "B", "A"]
    default = ["C", "B", "A"]


class LevelShuffle(Toggle):
    display_name = "Level Shuffle"


class LevelUnlockMethod(Choice):
    display_name = "Level Unlock Method"
    option_x_missions = 0
    option_unlock_item = 1
    default = 1


class LevelUnlockRange(Range):
    display_Name = "Level Unlock Mission Count"
    range_start = 5
    range_end = 20
    default = 20


class KingSpeedMultiplier(FloatRangeText):
    display_name = "King Speed Multiplier"
    range_start = 1.0
    range_end = 5.0
    default = 1.0


class CivilianSpeedMultiplier(FloatRangeText):
    display_name = "Civilian Speed Multiplier"
    range_start = 1.0
    range_end = 5.0
    default = 1.0

@dataclass
class SneakKingOptions(PerGameCommonOptions):
    death_link: DeathLink
    starting_level: StartingLevel