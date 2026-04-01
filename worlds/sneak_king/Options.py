from dataclasses import dataclass

from Options import PerGameCommonOptions, DeathLink, Choice, OptionSet, Toggle, Range, DefaultOnToggle


class Goal(Choice):
    """The win condition for the game.
    Complete X Missions: complete the required number of missions at any rank.
    Complete X A-Ranks: earn A-rank on the required number of missions."""
    display_name = "Goal"
    option_complete_x_missions = 0
    option_complete_x_a_ranks = 1
    default = 0


class GoalRange(Range):
    """The number of missions or A-ranks required to complete the goal."""
    display_name = "Goal Range"
    range_start = 10
    range_end = 80
    default = 40


class StartingLevel(Choice):
    """The level you start with access to. All other levels must be unlocked."""
    display_name = "Starting Level"
    option_sawmill = 0
    option_cul_de_sac = 1
    option_construction = 2
    option_downtown = 3
    default = 0


class EnabledRanks(OptionSet):
    """Which rank tiers count as locations. Disabling a rank removes those checks from the pool."""
    display_name = "Enabled Ranks"
    valid_keys = ["C", "B", "A"]
    default = ["C", "B", "A"]


class LevelUnlockMethod(Choice):
    """How non-starting levels are unlocked.
    Unlock Item: each level requires a specific unlock item from the item pool.
    X Missions: each level unlocks after completing a set number of missions in the previous level."""
    display_name = "Level Unlock Method"
    option_x_missions = 0
    option_unlock_item = 1
    default = 1


class LevelUnlockRange(Range):
    """When using the X Missions unlock method, the number of missions that must be completed
    in a level before the next level in the chain becomes accessible."""
    display_Name = "Level Unlock Mission Count"
    range_start = 5
    range_end = 20
    default = 10


class LevelShuffle(DefaultOnToggle):
    """Randomize the order in which levels appear in the unlock chain.
    When disabled, the unlock order is Sawmill -> Cul-De-Sac -> Construction -> Downtown.
    Only has an effect if the Level Unlock Method is set to X Missions."""
    display_name = "Level Shuffle"


class KingSpeedMultiplier(Range):
    """Multiplier applied to the King's movement speed."""
    display_name = "King Speed Multiplier"
    range_start = 1
    range_end = 2
    default = 1


class CivilianSpeedMultiplier(Range):
    """Multiplier applied to civilian movement speed."""
    display_name = "Civilian Speed Multiplier"
    range_start = 1
    range_end = 2
    default = 1


class TrapPercentage(Range):
    """Percentage of filler items replaced with traps."""
    display_name = "Trap Percentage"
    range_start = 0
    range_end = 100
    default = 0


@dataclass
class SneakKingOptions(PerGameCommonOptions):
    #death_link: DeathLink
    goal: Goal
    goal_range: GoalRange
    starting_level: StartingLevel
    enabled_ranks: EnabledRanks
    level_unlock_method: LevelUnlockMethod
    level_unlock_range: LevelUnlockRange
    level_shuffle: LevelShuffle
    #trap_percentage: TrapPercentage
    king_speed_multiplier: KingSpeedMultiplier
    civilian_speed_multiplier: CivilianSpeedMultiplier
