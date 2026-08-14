"""Archipelago world for Disney's Magical Mirror Starring Mickey Mouse (GameCube, GDME01).

Generation only, for now. There is no generate_output: the ROM half of the project
patches an ISO from H:\\Mickey\\mods plus build/ap_patch.json, and the client RAM
contract is not written yet, so a seed can be rolled and inspected but not played.
That is why the world is hidden.
"""

from typing import Any, ClassVar, Final, Mapping

from BaseClasses import Region
from Options import OptionError
from worlds.AutoWorld import WebWorld, World

from .Items import (MickeyItem, door_keys, item_list, item_table,
                    mickey_item_name_groups, tricks)
from .Locations import all_locations, get_locations_by_type
from .Options import KeyMode, MickeyOptions
from .Regions import connect_regions, create_regions
from .Rules import goal_condition, impassable_locations, load_rules, set_rules
from .Shuffle import build_requirements, door_pool_size, key_for

FILLER_ITEM: Final[str] = "Archipelago Item"

# Location type -> the option that turns those checks on. Types absent from this
# map are always checks: vessel, shard and key are the three counter pickups and
# the goal is measured in shards, so there is no seed without them, and the 15
# quest-item pickups are permanent by decision.
CHECK_OPTIONS: Final[Mapping[str, str]] = {
    "trick": "trick_checks",
    "hat_spot": "hat_spot_checks",
    "souvenir": "souvenir_checks",
}

# Souvenirs and the five hats are LOCATIONS ONLY. They stay defined in items.json
# because that is where the game's own item table lives and because every souvenir
# check names one as its `vanilla_item`, but none of them is ever placed: the check
# is the reward, and the ROM keeps granting the souvenir itself the way it always
# did. That is also why nothing needs suppressing on the ROM side.
#
# The consequence for the pool is that `flag` contributes nothing, so a full-options
# seed is mostly progression items and filler; see the note in create_items.
NOT_ITEMS: Final[str] = "flag"

# Turning a category of checks off leaves those pickups behaving as they do in the
# vanilla game, which means the pickup grants its own contents -- so the matching
# items must leave the pool, or the seed contains each of them twice. Only tricks
# are affected now that souvenirs and hats are not items, and tricks are keyed on
# `tricks` rather than `trick_checks`: that option is what decides whether a trick
# is an item at all, and the two are deliberately independent.
ITEMS_BY_OPTION: Final[Mapping[str, tuple[str, ...]]] = {
    "tricks": tricks,
}


class MickeyWebWorld(WebWorld):
    theme = "partyTime"


class MickeyWorld(World):
    """
    Mickey wakes to a mansion of living mirrors and a Mickey-shaped shadow that has
    taken his reflection. Learn tricks from the furniture, hunt down twelve mirror
    shards, and get your reflection back.
    """

    game = "Disney's Magical Mirror"
    web = MickeyWebWorld()
    options_dataclass = MickeyOptions
    options: MickeyOptions

    # Unhide once generate_output writes a patch and the client can play a seed.
    hidden = True

    item_name_to_id = {name: data.id for name, data in item_table.items()}
    location_name_to_id = {loc.name: loc.id for loc in all_locations}
    item_name_groups = mickey_item_name_groups
    location_name_groups = {
        "Trick": {loc.name for loc in get_locations_by_type("trick")},
        "Hat Spot": {loc.name for loc in get_locations_by_type("hat_spot")},
        "Souvenir": {loc.name for loc in get_locations_by_type("souvenir")},
        "Quest Item": {loc.name for loc in get_locations_by_type("quest_item")},
        "Star Container": {loc.name for loc in get_locations_by_type("vessel")},
        "Mirror Shard": {loc.name for loc in get_locations_by_type("shard")},
        "Small Key": {loc.name for loc in get_locations_by_type("key")},
    }

    # Archipelago's reachability root. The room the player actually starts in is
    # start_region_name, which Menu connects to; see Regions.connect_regions.
    origin_region_name = "Menu"
    start_region_name: ClassVar[str] = "area008"

    disabled_locations: set[str]
    created_regions: dict[str, Region]
    starting_containers: int
    # Locked doors and Small Keys are the same number by construction, so one
    # value drives both the pool and the door selection.
    key_count: int

    # Set by Shuffle.build_requirements, at the end of create_regions.
    trick_costs: dict[str, int]
    locked_doors: list[dict[str, Any]]
    unlocked_flags: list[int]
    location_requirements: dict[str, Any]
    entrance_requirements: dict[str, Any]

    def generate_early(self) -> None:
        self.disabled_locations = set()
        self.created_regions = {}

        # Checked here rather than in Shuffle because create_items runs first and
        # needs the key count, and because a bad value should stop generation
        # before any of the work.
        self.key_count = self.options.locked_door_count.value
        lockable = door_pool_size(load_rules().get("doors", []))
        if self.key_count > lockable:
            raise OptionError(
                f"Disney's Magical Mirror ({self.player_name}): Locked Door Count is "
                f"{self.key_count} but only {lockable} doors can carry a lock. That is "
                "every door the analysis can prove is an ordinary door; the rest are "
                "warp doors and trick warps, which have no lock to set.")

        self.starting_containers = min(self.options.starting_star_containers.value,
                                       item_table["Star Container"].frequency)
        for _ in range(self.starting_containers):
            self.multiworld.push_precollected(self.create_item("Star Container"))

    def create_regions(self) -> None:
        for loc in all_locations:
            option = CHECK_OPTIONS.get(loc.type)
            if option is not None and not getattr(self.options, option):
                self.disabled_locations.add(loc.name)
        self.disabled_locations |= impassable_locations()

        create_regions(self)
        connect_regions(self)

        # Requirements are decided here, not in set_rules, because create_items
        # runs in between and needs to know which doors ended up locked: in
        # per-door mode the pool holds those doors' keys and no others.
        self.location_requirements, self.entrance_requirements = \
            build_requirements(self)

    def create_items(self) -> None:
        skipped: set[str] = set()
        for option, items in ITEMS_BY_OPTION.items():
            if not getattr(self.options, option):
                skipped.update(items)

        # Keys are the one category the item table does not decide: which key items
        # exist and how many depends on the doors this seed locked. Everything else
        # comes from its frequency.
        keys: list[str] = [key_for(self, door) for door in self.locked_doors]
        skipped.update({"Small Key", *door_keys.values()})

        # Everything not in the pool: filler is added last to fit, souvenirs and
        # hats are checks rather than items, and keys were counted above.
        pool: list[str] = list(keys)
        for item in item_list:
            if item.grant in ("none", NOT_ITEMS) or item.item_name in skipped:
                continue
            copies = item.frequency
            if item.item_name == "Star Container":
                # Precollected containers come out of the pool, so the item and
                # location counts stay equal.
                copies -= self.starting_containers
            pool += [item.item_name] * copies

        checks = len(self.multiworld.get_unfilled_locations(self.player))
        if len(pool) > checks:
            raise OptionError(
                f"Disney's Magical Mirror ({self.player_name}): {len(pool)} items to place but "
                f"only {checks} checks to put them in. Turning a category of checks off without "
                "turning off the items it carries overfills the pool -- enable Hat Spot Checks "
                "(+59 checks), re-enable the checks you disabled, or disable Tricks (-38 items)."
                + (f" Locked Door Count is also adding {self.key_count - 8} key(s) over vanilla."
                   if self.key_count > 8 else ""))

        self.multiworld.itempool += [self.create_item(name) for name in pool]
        self.multiworld.itempool += [self.create_item(FILLER_ITEM) for _ in range(checks - len(pool))]

    def set_rules(self) -> None:
        set_rules(self)
        self.multiworld.completion_condition[self.player] = goal_condition(self)

    def create_item(self, name: str) -> MickeyItem:
        item = item_table[name]
        return MickeyItem(item.item_name, item.progression, item.id, self.player)

    def get_filler_item_name(self) -> str:
        return FILLER_ITEM

    def fill_slot_data(self) -> dict[str, Any]:
        # Option values only. What the client needs in order to write to the ROM --
        # flag ids, counter offsets, per-location grant sites -- is the RAM contract
        # (task #14) and is not settled yet.
        return {
            "tricks": self.options.tricks.value,
            "trick_checks": self.options.trick_checks.value,
            "hat_spot_checks": self.options.hat_spot_checks.value,
            "souvenir_checks": self.options.souvenir_checks.value,
            "shards_required": self.options.shards_required.value,
            "key_mode": self.options.key_mode.value,
            "locked_door_count": self.key_count,
            "starting_star_containers": self.starting_containers,
            "entrance_shuffle": self.options.entrance_shuffle.value,
            "death_link": self.options.death_link.value,
            # trick id -> star containers required, one byte per trick in the ROM
            # (the low 7 bits of the trick_set p5 payload). Sent even when the
            # option is off, so the client never has to know the vanilla table.
            "trick_costs": self.trick_costs,
            # Doors that need a key: their event flag where they have one, and the
            # areaNNN:wpXX sides to install the lock on.
            "locked_doors": [{"id": door["id"], "flag": door["flag"],
                              "sides": door["sides"]} for door in self.locked_doors],
            # Vanilla locks that are gone. These flags must be SET on a new file,
            # which is what makes the door start open.
            "unlocked_door_flags": self.unlocked_flags,
        }
