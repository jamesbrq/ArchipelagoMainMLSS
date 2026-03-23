from dataclasses import dataclass

from Options import PerGameCommonOptions, DeathLink, Choice, OptionSet, Toggle, Range, DefaultOnToggle


class Goal(Choice):
    display_name = "Goal"
    option_complete_x_missions = 0
    option_complete_x_a_ranks = 1
    default = 0


class GoalRange(Range):
    display_name = "Goal Range"
    range_start = 10
    range_end = 80
    default = 20


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


class LevelShuffle(DefaultOnToggle):
    display_name = "Level Shuffle"


class KingSpeedMultiplier(Range):
    display_name = "King Speed Multiplier"
    range_start = 1
    range_end = 5
    default = 1


class CivilianSpeedMultiplier(Range):
    display_name = "Civilian Speed Multiplier"
    range_start = 1
    range_end = 5
    default = 1


class TrapPercentage(Range):
    display_name = "Trap Percentage"
    range_start = 0
    range_end = 100
    default = 0


@dataclass
class SneakKingOptions(PerGameCommonOptions):
    death_link: DeathLink
    goal: Goal
    goal_range: GoalRange
    starting_level: StartingLevel
    enabled_ranks: EnabledRanks
    level_unlock_method: LevelUnlockMethod
    level_unlock_range: LevelUnlockRange
    level_shuffle: LevelShuffle
    trap_percentage: TrapPercentage
    king_speed_multiplier: KingSpeedMultiplier
    civilian_speed_multiplier: CivilianSpeedMultiplier
