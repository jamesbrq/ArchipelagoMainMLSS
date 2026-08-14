"""Trick cost shuffle and locked door relocation.

Both options work by rewriting the requirement dicts from json/rules.json BEFORE
Rules.set_rules turns them into lambdas. That keeps one place deciding what a rule
says and one place attaching it, and it means the shuffles are checked against the
same grammar the rules are built from.

The registries they need -- which rule sites belong to which trick, and which
entrances belong to one physical door -- are generated into rules.json by
tools/gen_ap_rules.py, because neither is derivable from the apworld alone: an
entrance's name is assigned by that generator, and the door and trick tags live in
data/ap_rules.json, which the apworld does not ship.
"""

import typing
from typing import Any, Final

from Options import OptionError

from .Items import door_keys
from .Options import KeyMode
from .Regions import all_entrances, locations_by_region
from .Rules import GOAL_REGION, evaluate, load_rules

if typing.TYPE_CHECKING:
    from . import MickeyWorld

KEY: Final[str] = "Small Key"
VESSEL: Final[str] = "Star Container"

# Every copy of the counted items other than keys, of which there are as many as
# there are locked doors. Used as "all state" for the guard: if the whole map is not
# reachable holding all of them, no placement can rescue it.
CAPS: Final[dict[str, int]] = {VESSEL: 12, "Mirror Shard": 12}

# How many door layouts to try before giving up. A pathological roll is one that
# strands the keys behind their own doors; with 8 locks over 39 candidates that is
# uncommon, so a run of this many failures means something structural, not luck.
DOOR_ATTEMPTS: Final[int] = 200

# Costs the `random` setting rolls between. 0 is excluded deliberately: a free
# trick is a vanilla quirk (trick_06 alone), not something to hand out at random.
RANDOM_COST_RANGE: Final[tuple[int, int]] = (1, 4)


def build_requirements(world: "MickeyWorld") -> tuple[dict[str, Any], dict[str, Any]]:
    """(location requirements, entrance requirements) with both shuffles applied.

    Also records the assignments on the world, for fill_slot_data -- the ROM side
    needs the trick cost bytes and the door lock list, and neither is recoverable
    from the rules afterwards.
    """
    raw = load_rules()
    locations = dict(raw.get("locations", {}))
    entrances = dict(raw.get("entrances", {}))

    world.trick_costs = _shuffle_trick_costs(world, raw.get("tricks", {}),
                                             locations, entrances)
    world.locked_doors, world.unlocked_flags = _choose_locks(
        world, raw.get("doors", []), locations, entrances)
    return locations, entrances


# ------------------------------------------------------------------ trick costs

def _shuffle_trick_costs(world: "MickeyWorld", tricks: dict[str, Any],
                         locations: dict, entrances: dict) -> dict[str, int]:
    """Reassign every trick's star cost, and rewrite the rules that quote it.

    A trick costs 5 x cost trick points and capacity is 5 x containers, so the
    cost IS the number of Star Containers you must hold. Only 10 rule sites in the
    ruleset quote a cost, so most of this assignment is carried for the ROM and has
    no effect on logic -- see the note in fill_slot_data.
    """
    vanilla = {tid: rec["cost"] for tid, rec in tricks.items()}
    mode = world.options.trick_cost_shuffle
    if mode == mode.option_off:
        return vanilla

    ids = sorted(vanilla)
    if mode == mode.option_shuffle:
        # Permute the vanilla multiset: the same 18 ones, 12 twos, 6 threes, one
        # four and one free trick, dealt to different tricks. Total cost across the
        # game is unchanged, so this cannot inflate what the seed demands.
        costs = [vanilla[t] for t in ids]
        world.random.shuffle(costs)
        assigned = dict(zip(ids, costs))
    else:
        lo, hi = RANDOM_COST_RANGE
        assigned = {t: world.random.randint(lo, hi) for t in ids}

    for tid, rec in tricks.items():
        cost = assigned[tid]
        if cost == vanilla[tid]:
            continue
        for name in rec["locations"]:
            if name in locations:
                locations[name] = _set_count(locations[name], VESSEL, cost)
        for name in rec["entrances"]:
            if name in entrances:
                entrances[name] = _set_count(entrances[name], VESSEL, cost)
    return assigned


# ------------------------------------------------------------------ door locks

def door_pool_size(doors: list[dict[str, Any]]) -> int:
    return sum(1 for d in doors if d["pool"])


def _choose_locks(world: "MickeyWorld", doors: list[dict[str, Any]],
                  locations: dict, entrances: dict
                  ) -> tuple[list[dict[str, Any]], list[int]]:
    """Pick which doors are locked, and rewrite the rules to match.

    The lock unit is a physical door, not a doorway: a door has up to two sides
    and unlocking it from either sets the same event flag, so both sides move
    together. Candidates are the doors the analysis marks as installed by
    door_open_set with no key check -- the ones a lock could be installed on
    instead. Warp doors and trick warps are not doors and are not in the pool.

    How the count and the shuffle flag combine:

      * shuffle off, count 8   -- the vanilla doors, untouched. Fast path.
      * shuffle off, count < 8 -- that many of the vanilla doors, chosen at random;
                                  the rest start open.
      * shuffle off, count > 8 -- all 8 vanilla doors plus extras from the pool.
      * shuffle on             -- that many drawn from the whole pool, vanilla
                                  doors included but with no head start.

    Rolls are checked before being accepted, because there is exactly one key per
    locked door and no slack: a layout that puts every key behind a lock is
    unsolvable, and letting it through would surface much later as a fill failure
    with no explanation.
    """
    vanilla = [d for d in doors if d["vanilla_locked"]]
    pool = [d for d in doors if d["pool"]]
    count = world.key_count

    # Vanilla in every respect -- same doors, same generic key -- so the rules are
    # already right and nothing needs rewriting. Per-door mode does NOT qualify: the
    # doors are the same but the item that opens each one is not.
    if (not world.options.locked_door_shuffle and count == len(vanilla)
            and world.options.key_mode != KeyMode.option_per_door):
        return vanilla, []

    if world.options.locked_door_shuffle:
        candidates, base = pool, []
    elif count <= len(vanilla):
        candidates, base = vanilla, []
    else:
        base = list(vanilla)
        candidates = [d for d in pool if not d["vanilla_locked"]]
    take = count - len(base)

    for _ in range(DOOR_ATTEMPTS):
        chosen = base + world.random.sample(candidates, take)
        locs, ents = _apply_locks(world, doors, chosen, locations, entrances)
        if _solvable(world, locs, ents, chosen):
            locations.clear()
            locations.update(locs)
            entrances.clear()
            entrances.update(ents)
            # The vanilla doors that are no longer locked have to START open, which
            # on the ROM side is their event flag pre-set in the flag bank.
            still = {d["id"] for d in chosen}
            unlocked = [d["flag"] for d in vanilla if d["id"] not in still]
            return chosen, unlocked
        if take in (0, len(candidates)):
            break  # only one possible set, so retrying samples the same thing

    raise OptionError(
        f"Disney's Magical Mirror ({world.player_name}): could not find a solvable "
        f"layout for {count} locked door(s) in {DOOR_ATTEMPTS} attempts. Every layout "
        "tried left a key unreachable behind its own lock. Re-roll the seed, lower "
        "Locked Door Count, or turn Locked Door Shuffle off.")


def key_for(world: "MickeyWorld", door: dict[str, Any]) -> str:
    """The item that opens this door: one generic key, or the door's own."""
    if world.options.key_mode == KeyMode.option_per_door:
        return door_keys.get(door["id"], KEY)
    return KEY


def _apply_locks(world: "MickeyWorld", doors: list[dict[str, Any]],
                 chosen: list[dict[str, Any]], locations: dict,
                 entrances: dict) -> tuple[dict, dict]:
    """Requirements with every key term removed, then re-added to `chosen` only.

    Stripping covers the generic key AND every per-door key, so switching modes
    cannot leave a stale requirement behind for an item the pool no longer holds.
    """
    keys = {KEY, *door_keys.values()}
    locs, ents = dict(locations), dict(entrances)
    for door in doors:
        for name in door["entrances"]:
            if name in ents:
                stripped = _without(ents[name], keys)
                if stripped is True:
                    ents.pop(name)
                else:
                    ents[name] = stripped
    for door in chosen:
        item = key_for(world, door)
        for name in door["entrances"]:
            ents[name] = _with_count(ents.get(name, True), item, 1)
    return locs, ents


def _solvable(world: "MickeyWorld", locations: dict, entrances: dict,
              chosen: list[dict[str, Any]]) -> bool:
    """Two structural tests, cheapest first.

    1. Holding every key, container and shard, the goal and every enabled check
       must be reachable. `accessibility: full` demands exactly this, so a layout
       failing it cannot generate no matter how items are placed.
    2. The key economy has to bootstrap. Starting with nothing, repeatedly assume
       the checks you can already reach could hold the items you need, and see
       whether that grows to the full set. This is the optimism Archipelago's own
       fill operates under -- it places progression where you can reach it -- so a
       layout that passes may still fail to fill, but one that fails here cannot
       work at all.
    """
    start = world.start_region_name
    enabled = [loc for region in locations_by_region
               for loc in locations_by_region[region]
               if loc.name not in world.disabled_locations]
    # One key per locked door. In vanilla mode that is `key_count` generic keys; in
    # per-door mode it is one of each chosen door's own key, which is the same
    # number of items but not interchangeable -- so the guard has to hold the
    # specific ones, or a per-door layout would be judged against a key that opens
    # anything.
    all_items = dict(CAPS)
    for door in chosen:
        item = key_for(world, door)
        all_items[item] = all_items.get(item, 0) + 1

    reached = _sweep(entrances, all_items, start)
    if GOAL_REGION not in reached:
        return False
    for loc in enabled:
        if loc.region not in reached or not evaluate(locations.get(loc.name, True),
                                                    all_items):
            return False

    # The reachable checks are a shared budget: n checks can hold n items and no
    # more. Keys are drawn first and only for doors ON THE FRONTIER -- a door with a
    # side in the reached set. That distinction only matters in per-door mode, where
    # handing out keys in any fixed order would grant one for a door on the far side
    # of the map and call a stuck layout solvable, or refuse a workable one because
    # the key it needed sorted last.
    frm_of = {entrance.name: entrance.frm for entrance in all_entrances}
    counts = {item: 0 for item in all_items}
    while counts != all_items:
        reached = _sweep(entrances, counts, start)
        budget = sum(1 for loc in enabled if loc.region in reached
                     and evaluate(locations.get(loc.name, True), counts))

        grown = {item: 0 for item in all_items}
        for door in chosen:
            if budget <= 0:
                break
            if any(frm_of.get(name) in reached for name in door["entrances"]):
                item = key_for(world, door)
                if grown[item] < all_items[item]:
                    grown[item] += 1
                    budget -= 1
        for item in CAPS:
            grown[item] = min(all_items[item], max(0, budget))
            budget -= grown[item]

        # Accumulate rather than replace: what you could once have obtained you
        # still have, and it keeps this loop monotone so it always terminates.
        grown = {item: max(counts[item], grown[item]) for item in all_items}
        if grown == counts:
            return False
        counts = grown
    return True


def _sweep(entrances: dict, counts: dict[str, int], start: str) -> set[str]:
    """Regions reachable from `start` while holding `counts`."""
    reached, frontier = {start}, [start]
    while frontier:
        region = frontier.pop()
        for entrance in all_entrances:
            if entrance.frm != region or entrance.to in reached:
                continue
            if evaluate(entrances.get(entrance.name, True), counts):
                reached.add(entrance.to)
                frontier.append(entrance.to)
    return reached


# ------------------------------------------------- requirement dict surgery

def _set_count(req: Any, item: str, count: int) -> Any:
    """Rewrite every `has item` count in `req`. count 0 satisfies it outright."""
    if isinstance(req, dict):
        if "has" in req:
            value = req["has"]
            named = value.get("item") if isinstance(value, dict) else value
            if named == item:
                return True if count <= 0 else {"has": {"item": item, "count": count}}
            return req
        return {op: [_set_count(c, item, count) for c in terms]
                for op, terms in req.items()}
    return req


def _without(req: Any, items: set[str]) -> Any:
    """`req` with every `has` term naming one of `items` satisfied, then simplified."""
    if isinstance(req, dict):
        if "has" in req:
            value = req["has"]
            named = value.get("item") if isinstance(value, dict) else value
            return True if named in items else req
        for op, terms in req.items():
            rebuilt = [_without(c, items) for c in terms]
            if op == "or":
                if any(c is True for c in rebuilt):
                    return True
                rebuilt = [c for c in rebuilt if c is not False]
                if not rebuilt:
                    return False
                return rebuilt[0] if len(rebuilt) == 1 else {"or": rebuilt}
            if op == "and":
                if any(c is False for c in rebuilt):
                    return False
                rebuilt = [c for c in rebuilt if c is not True]
                if not rebuilt:
                    return True
                return rebuilt[0] if len(rebuilt) == 1 else {"and": rebuilt}
            return req
    return req


def _with_count(req: Any, item: str, count: int) -> Any:
    term = {"has": {"item": item, "count": count}}
    if req is True or req is None:
        return term
    return {"and": [req, term]}
