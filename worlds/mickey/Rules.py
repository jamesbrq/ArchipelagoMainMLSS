import json
import pkgutil
import typing
from typing import Final

from worlds.generic.Rules import add_rule

if typing.TYPE_CHECKING:
    from BaseClasses import CollectionState

    from . import MickeyWorld


# The goal, transcribed from the `goal` record in H:\Mickey\data\ap_rules.json.
# That record is not generated into json/rules.json -- tools/gen_ap_rules.py emits
# only `locations` and `entrances` -- so this is the one rule in the world that is
# hand-written, and it has to be re-checked by hand if the goal analysis moves.
#
# The goal region is area008, entered from area051, and area008 is ALSO the start
# region, so its reachability proves nothing: what has to be reached is area051,
# the endgame variant of the mirror room, which is the only region with an edge
# into area008. Its own entrance rules already demand 8 shards, because that is
# the count area012.rel tests before flipping the warp tables -- so a
# shards_required below 8 does not actually shorten the seed until the ROM side
# patches that test.
GOAL_REGION: Final[str] = "Mirror Room (Endgame Variant)"


def load_rules() -> dict:
    return json.loads(pkgutil.get_data(__name__, "json/rules.json").decode())


def impassable_locations() -> frozenset[str]:
    """Checks whose requirement is `false`.

    tools/gen_ap_rules.py fails closed, so `false` means "we have not classified
    this yet", not "this is provably impossible". The world drops these rather
    than shipping a check nobody can ever reach; they come back on their own once
    the generator can express the requirement (task #26).
    """
    return frozenset(name for name, requirement in load_rules().get("locations", {}).items()
                     if requirement is False)


def goal_condition(world: "MickeyWorld") -> typing.Callable[["CollectionState"], bool]:
    player = world.player
    shards = world.options.shards_required.value
    return lambda state: (state.has("Mirror Shard", player, shards)
                          and state.can_reach_region(GOAL_REGION, player))


def evaluate(requirement, counts: typing.Mapping[str, int]) -> bool:
    """The same grammar as _expression, decided against a plain item->count map.

    Used by Shuffle to test a candidate door layout before it is committed, which
    has to happen before there is any CollectionState to ask. Unrecognised shapes
    are False, for the reason given in _expression: a requirement we cannot read
    must make things unreachable, not free.
    """
    if requirement is True:
        return True
    if requirement is False or requirement is None:
        return False

    if "or" in requirement:
        return any(evaluate(c, counts) for c in requirement["or"])
    if "and" in requirement:
        return all(evaluate(c, counts) for c in requirement["and"])
    if "has" in requirement:
        value = requirement["has"]
        if isinstance(value, dict):
            item, count = value.get("item", ""), value.get("count", 1)
        else:
            item, count = value, requirement.get("count", 1)
        return counts.get(item, 0) >= count
    return False


def set_rules(world: "MickeyWorld") -> None:
    """Attach access rules to checks and to entrances.

    The requirements were built in create_regions by Shuffle.build_requirements
    rather than read from json/rules.json here, because the trick-cost and
    locked-door options rewrite them and create_items has to see the result. With
    those options off they are the file's contents unchanged.
    """
    locations, entrances = world.location_requirements, world.entrance_requirements

    for location, requirement in locations.items():
        if location in world.disabled_locations:
            continue
        add_rule(world.get_location(location), _build_rule(requirement, world))

    for entrance, requirement in entrances.items():
        # connect_regions has run by now, so every entrance named in rules.json
        # must exist. A KeyError here means the two files disagree about a name,
        # which would silently drop an access rule -- fail instead.
        add_rule(world.multiworld.get_entrance(entrance, world.player),
                 _build_rule(requirement, world))


def _build_rule(requirement, world: "MickeyWorld") -> typing.Callable:
    """One requirement -> a lambda over CollectionState."""
    return eval(f"lambda state: {_expression(requirement)}", {"world": world})


def _expression(r) -> str:
    """Requirement dict -> a Python expression string.

    Grammar, produced by tools/gen_ap_rules.py:
        {"and": [...]}   {"or": [...]}
        {"has": {"item": name, "count": n}}
        false                                   impassable

    `{"function": ...}` is reserved but has no implementation: the generator has
    never emitted one, so there is no helper module to dispatch to. It raises here
    rather than eval'ing a name that does not exist, which would fail later, once
    per rule evaluation, with no indication of where it came from.

    An unrecognised shape becomes False rather than True. That direction matters:
    a requirement we cannot read must make content unreachable, not free. The
    same reasoning is why the generator maps UNKNOWN edges to false.
    """
    if r is False or r is None:
        return "False"
    if r is True:
        return "True"

    if "or" in r:
        return f"({' or '.join(_expression(c) for c in r['or'])})"
    if "and" in r:
        return f"({' and '.join(_expression(c) for c in r['and'])})"

    if "has" in r:
        value = r["has"]
        if isinstance(value, dict):
            item, count = value.get("item", ""), value.get("count", 1)
        else:
            item, count = value, r.get("count", 1)
        if count == 1:
            return f"state.has({item!r}, world.player)"
        return f"state.has({item!r}, world.player, {int(count)})"

    if "function" in r:
        raise ValueError(f"json/rules.json requires function {r['function']!r}, "
                         "which no rule helper implements")

    return "False"
