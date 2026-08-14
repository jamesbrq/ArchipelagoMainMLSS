from dataclasses import dataclass

from Options import Choice, DeathLink, DefaultOnToggle, PerGameCommonOptions, Range, StartInventoryPool, Toggle


class Tricks(DefaultOnToggle):
    """
    Tricks will be added to the pool as items, and each trick's interaction is
    locked until you receive it.
    There are 38 tricks. Six of them are the only route into an area, so with this
    enabled they become progression items.
    Disabling this leaves every trick performable from the start.
    """
    display_name = "Tricks"


class TrickChecks(DefaultOnToggle):
    """
    Performing a trick for the first time is a check.
    38 locations. Independent of the Tricks option: you can shuffle the checks
    without locking the tricks themselves, or the reverse.
    """
    display_name = "Trick Checks"


class HatSpotChecks(Toggle):
    """
    The 59 hat-hiding spots become checks, and every one is filled.
    In the real game you hide 5 hats and find them again later, so only 5 of the
    59 spots ever hold anything. Enabling this fills all of them, which adds 59
    locations -- the single largest category in the game.
    """
    display_name = "Hat Spot Checks"


class SouvenirChecks(DefaultOnToggle):
    """
    The 24 souvenirs become checks.
    Souvenirs are pure collectibles; none of them is known to gate anything.
    """
    display_name = "Souvenir Checks"


class TrickCostShuffle(Choice):
    """
    Randomize what each trick costs in stars.
    A trick costs five points per unit and your capacity is five points per star
    container, so a trick's cost is really the number of containers you must own to
    perform it at all. Vanilla spreads 38 tricks over one free trick, 18 costing
    one container, 12 costing two, 6 costing three and one costing four.
    Shuffle: deal those same costs out to different tricks. The total the game asks
    of you is unchanged, only which rooms are expensive.
    Randomized: roll every trick independently between 1 and 4, which asks for
    considerably more than vanilla and can make an early trick expensive.
    Only 10 access rules quote a trick's cost today, so most of this changes what
    the game charges you and not what the logic expects.
    """
    display_name = "Trick Cost Shuffle"
    option_off = 0
    option_shuffle = 1
    option_randomized = 2
    default = 0


class LockedDoorCount(Range):
    """
    How many doors are locked, and how many keys exist.
    The two move together: every locked door costs exactly one key and the pool
    holds one key per locked door, so there are never spares and never a door you
    cannot open. Vanilla is 8 of each.
    Below 8, doors are dropped from the vanilla set and start open. Above 8, extra
    doors are locked, drawn from the 35 the analysis can prove are ordinary doors --
    which is also the ceiling. At 0 nothing is locked and no keys are in the pool.
    Raising this makes keys a much larger share of the item pool, so with few checks
    enabled a high count can ask for more items than there are places to put them.
    """
    display_name = "Locked Door Count"
    range_start = 0
    range_end = 35
    default = 8


class LockedDoorShuffle(Toggle):
    """
    Move the key locks onto a different set of doors.
    The doors that need a key in vanilla start open, and the same number of other
    doors are locked instead, drawn from the 35 the analysis can prove are ordinary
    doors. How many is Locked Door Count.
    A door's two sides move together, because unlocking one unlocks both.
    There is exactly one key per locked door and no spares, so a layout that
    strands a key behind its own lock is unsolvable; layouts are tested before
    being accepted and generation fails rather than shipping a dead seed.
    """
    display_name = "Locked Door Shuffle"


class ShardsRequired(Range):
    """
    How many Mirror Shards are needed to finish.
    The game requires all 12: the final room sends you to the results screen
    instead of the ending unless the counter reads exactly 12. Lowering this
    shortens the seed.
    """
    display_name = "Shards Required"
    range_start = 1
    range_end = 12
    default = 12


class KeyMode(Choice):
    """
    How locked doors work.
    Vanilla: one generic Small Key item, spent on any door, as the game does it.
    Keys and doors are equal in number with no spares, so every key matters and a
    key spent early is a key you do not have later.
    Per Door: each locked door gets its own key, named for the two rooms it joins,
    and no counter is involved. The pool is the same size either way -- one key per
    locked door -- but a key you find is only ever useful on one door, which makes
    routing more legible and cannot strand you on a door you already paid for.
    """
    display_name = "Key Mode"
    option_vanilla = 0
    option_per_door = 1
    default = 0


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
    Only Arrival Points is offered. Rewiring a door to a different ROOM breaks the
    game -- the destination's own entry conditions no longer hold, which was
    confirmed in testing (wrong room, broken scripts, no Mickey), and Archipelago's
    entrance randomization has no way to express an arrival condition either.
    """
    display_name = "Entrance Shuffle"
    option_off = 0
    option_arrival_points = 1
    default = 0


@dataclass
class MickeyOptions(PerGameCommonOptions):
    start_inventory_from_pool: StartInventoryPool
    tricks: Tricks
    trick_checks: TrickChecks
    hat_spot_checks: HatSpotChecks
    souvenir_checks: SouvenirChecks
    trick_cost_shuffle: TrickCostShuffle
    locked_door_count: LockedDoorCount
    locked_door_shuffle: LockedDoorShuffle
    shards_required: ShardsRequired
    key_mode: KeyMode
    starting_star_containers: StartingStarContainers
    entrance_shuffle: EntranceShuffle
    death_link: DeathLink
