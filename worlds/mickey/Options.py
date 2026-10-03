from dataclasses import dataclass

from Options import Choice, DeathLink, DefaultOnToggle, PerGameCommonOptions, Range, StartInventoryPool, Toggle


class Tricks(DefaultOnToggle):
    """
    Tricks will be added to the pool as items, and each trick's interaction is
    locked until you receive it.
    There are 33 unlock items. Some unlock multiple stages or alternate paths
    of the same trick. Tricks needed to reach new areas are progression items.
    Disabling this leaves every trick performable from the start.
    """
    display_name = "Tricks"


class TrickChecks(DefaultOnToggle):
    """
    Performing a trick for the first time is a check.
    36 locations. Independent of the Tricks option: you can shuffle the checks
    without locking the tricks themselves, or the reverse.
    """
    display_name = "Trick Checks"


class HiddenHats(Toggle):
    """Add the 30 hidden hat boxes as checks, three in each of ten rooms.

    Reveal a box using its room interaction, then open it to collect the placed
    item. Disabled removes these locations from generation and hides the boxes
    in-game. The original boxes and their opening animations are preserved.
    """
    display_name = "Hidden Hats"


class TrickCostShuffle(Choice):
    """
    Randomize what each trick costs in stars.
    A trick costs five points per unit and your capacity is five points per star
    container, so a trick's cost is really the number of containers you must own to
    perform it at all. The active vanilla tricks cost between one and four
    containers. Separate stages and alternate paths retain individual costs.
    Shuffle: deal those same per-trick costs out to different tricks.
    Randomized: roll every trick between 1 and 4, which asks for
    considerably more than vanilla and can make an early trick expensive.
    Each trick check requires its assigned capacity, as do the tagged routes
    and rewards that depend on that trick. The assigned costs are written into
    both script and compiled registrations when patching the game.
    Cost assignments keep mandatory consecutive sequences within twelve
    containers, including Lever plus three Clock Face activations for its reward.
    """
    display_name = "Trick Cost Shuffle"
    option_off = 0
    option_shuffle = 1
    option_randomized = 2
    default = 0


class LockedDoorCount(Range):
    """
    Number of locked doors, each with its own matching key in the pool.
    With Vanilla locked doors, fewer than 7 selects a random subset of the
    seven eligible vanilla locks; more than 7 adds random extra doors.
    With Randomized locked doors, the whole set is chosen randomly.
    Both Mirror Room doors always start unlocked.
    At 0 nothing is locked and no keys are in the pool. Maximum: 28.
    Raising this makes keys a much larger share of the item pool, so with few checks
    enabled a high count can ask for more items than there are places to put them.
    """
    display_name = "Locked Door Count"
    range_start = 0
    range_end = 28
    default = 8


class LockedDoors(Choice):
    """
    Choose where locks appear. Every locked door uses its own matching key.
    Vanilla: use the seven eligible vanilla locks; Locked Door Count can remove
    some or add random extra doors while retaining all seven.
    Randomized: choose from all 28 eligible two-way doors.
    Both Mirror Room doors always start unlocked in either mode.
    Both sides of a physical door share a lock. Locked Door Count controls
    the number of locks and matching keys in either mode.
    """
    display_name = "Locked Doors"
    option_vanilla = 0
    option_randomized = 1
    default = 0


class ShardsRequired(Range):
    """
    How many Mirror Shards are needed to finish.
    The ending and its Mirror Room route require at least this many shards.
    Collecting additional shards will not prevent completion. Souvenirs which
    require all twelve shards retain that requirement.
    """
    display_name = "Shards Required"
    range_start = 1
    range_end = 12
    default = 12


class StartingStarContainers(Range):
    """
    How many Star Containers to start with.
    A real new game starts with zero, and trick point capacity is your container
    count times five -- so with none, exactly one trick in the game is
    performable. Starting with a few opens up early tricks.
    """
    display_name = "Starting Star Containers"
    range_start = 0
    range_end = 12
    default = 0


class EntranceShuffle(Choice):
    """
    Shuffle where doors lead.
    Off: doors go where they always did.
    Arrival Points: a door still leads to the same room, but you arrive at a
    different point inside it.
    Ordinary Doors: shuffle audited two-way doors with matching return paths.
    Locked doorways shuffle with locked doorways and share one key per new pair.
    Arrival Points preserves each door's original key. Broken Room - Spa Room
    shuffles its first Pole crossing and repeat door together; both Pole parts
    and their combined cost remain required on the Broken Room side. Other
    quest-gated doors, special free returns and scripted routes stay fixed.
    Flying Sword follows the shuffled Basement doorway on its first use.
    The Mirror Room - Hole Room doorway shuffles as one pair across its room
    versions; the Mirror Room - Entrance doorway remains fixed. Logic first
    introduces Broken Room through its Old Hall-side entrance and Storage Room
    through its Dark Hallway-side entrance.
    """
    display_name = "Entrance Shuffle"
    option_off = 0
    option_arrival_points = 1
    option_ordinary_doors = 2
    default = 0


class Costume(Choice):
    """Mickey's appearance. Cosmetic only; applied to your own game during patching."""
    display_name = "Costume"
    option_original = 0
    option_black_hooded_cloak = 1
    option_steamboat_willie = 2
    option_sorcerer = 3
    default = 0


@dataclass
class MickeyOptions(PerGameCommonOptions):
    costume: Costume
    start_inventory_from_pool: StartInventoryPool
    tricks: Tricks
    trick_checks: TrickChecks
    hidden_hats: HiddenHats
    trick_cost_shuffle: TrickCostShuffle
    locked_door_count: LockedDoorCount
    locked_doors: LockedDoors
    shards_required: ShardsRequired
    starting_star_containers: StartingStarContainers
    entrance_shuffle: EntranceShuffle
