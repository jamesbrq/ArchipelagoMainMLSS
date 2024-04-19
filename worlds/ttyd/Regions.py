import typing

from BaseClasses import Region, Entrance
from .Locations import (TTYDLocation, rogueport, sewers, petal_left, petal_right, hooktails_castle,
                        boggly_woods, great_tree, glitzville, twilight_trail, twilight_town,
                        creepy_steeple, keelhaul_key, pirates_grotto, excess_express, riverside,
                        poshley_heights, fahr_outpost, xnaut_fortress, palace, pit, rogueport_westside)
from . import StateLogic

if typing.TYPE_CHECKING:
    from . import TTYDWorld


def create_regions(world: "TTYDWorld", excluded: typing.List[str]):
    menu_region = Region("Menu", world.player, world.multiworld)
    world.multiworld.regions.append(menu_region)

    create_region(world, "Rogueport", rogueport, excluded)
    create_region(world, "Rogueport (Westside)", rogueport_westside, excluded)
    create_region(world, "Rogueport Sewers", sewers, excluded)
    create_region(world, "Petal Meadows (Left)", petal_left, excluded)
    create_region(world, "Petal Meadows (Right)", petal_right, excluded)
    create_region(world, "Hooktail's Castle", hooktails_castle, excluded)
    create_region(world, "Boggly Woods", boggly_woods, excluded)
    create_region(world, "Great Tree", great_tree, excluded)
    create_region(world, "Glitzville", glitzville, excluded)
    create_region(world, "Twilight Town", twilight_town, excluded)
    create_region(world, "Twilight Trail", twilight_trail, excluded)
    create_region(world, "Creepy Steeple", creepy_steeple, excluded)
    create_region(world, "Keelhaul Key", keelhaul_key, excluded)
    create_region(world, "Pirate's Grotto", pirates_grotto, excluded)
    create_region(world, "Excess Express", excess_express, excluded)
    create_region(world, "Riverside Station", riverside, excluded)
    create_region(world, "Poshley Heights", poshley_heights, excluded)
    create_region(world, "Fahr Outpost", fahr_outpost, excluded)
    create_region(world, "X-Naut Fortress", xnaut_fortress, excluded)
    create_region(world, "Palace of Shadow", palace, excluded)
    create_region(world, "Pit of 100 Trials", pit, excluded)


def connect_regions(world: "TTYDWorld"):
    names: typing.Dict[str, int] = {}

    connect(world, names, "Menu", "Rogueport")
    connect(world, names, "Rogueport", "Rogueport Sewers")
    connect(world, names, "Rogueport", "Palace of Shadow", lambda state: StateLogic.palace(state, world.player, 7))
    connect(world, names, "Rogueport", "Poshley Heights", lambda state: state.has("Ultra Hammer", world.player) and state.has("Super Boots", world.player))
    connect(world, names, "Rogueport", "Fahr Outpost", lambda state: StateLogic.fahr_outpost(state, world.player))
    connect(world, names, "Rogueport", "Keelhaul Key", lambda state: StateLogic.keelhaul_key(state, world.player))
    connect(world, names, "Keelhaul Key", "Pirate's Grotto", lambda state: StateLogic.pirates_grottos(state, world.player))
    connect(world, names, "Rogueport", "Rogueport (Westside)", lambda state: StateLogic.westside(state, world.player))
    connect(world, names, "Rogueport (Westside)", "Glitzville", lambda state: StateLogic.glitzville(state, world.player))
    connect(world, names, "Rogueport (Westside)", "Excess Express", lambda state: StateLogic.excess_express(state, world.player))
    connect(world, names, "Excess Express", "Riverside Station", lambda state: StateLogic.riverside(state, world.player))
    connect(world, names, "Riverside Station", "Poshley Heights", lambda state: StateLogic.poshley_heights(state, world.player))
    connect(world, names, "Rogueport Sewers", "Petal Meadows (Left)", lambda state: StateLogic.petal_left(state, world.player))
    connect(world, names, "Rogueport Sewers", "Boggly Woods", lambda state: StateLogic.boggly_woods(state, world.player))
    connect(world, names, "Rogueport Sewers", "Twilight Town", lambda state: StateLogic.twilight_town(state, world.player))
    connect(world, names, "Twilight Town", "Twilight Trail", lambda state: StateLogic.twilight_trail(state, world.player))
    connect(world, names, "Twilight Trail", "Creepy Steeple", lambda state: StateLogic.steeple(state, world.player))
    connect(world, names, "Rogueport Sewers", "Petal Meadows (Right)", lambda state: StateLogic.petal_right(state, world.player))
    connect(world, names, "Petal Meadows (Left)", "Petal Meadows (Right)")
    connect(world, names, "Petal Meadows (Left)", "Hooktail's Castle", lambda state: StateLogic.hooktails_castle(state, world.player))
    connect(world, names, "Boggly Woods", "Great Tree", lambda state: StateLogic.great_tree(state, world.player))
    connect(world, names, "Fahr Outpost", "X-Naut Fortress", lambda state: StateLogic.moon(state, world.player))


def create_region(world: "TTYDWorld", name, locations, excluded):
    ret = Region(name, world.player, world.multiworld)
    for location in locations:
        loc = TTYDLocation(world.player, location.name, location.id, ret)
        if location.name in excluded:
            continue
        ret.locations.append(loc)
    world.multiworld.regions.append(ret)


def connect(world: "TTYDWorld", used_names: typing.Dict[str, int], source: str, target: str,
            rule: typing.Optional[typing.Callable] = None):
    source_region = world.multiworld.get_region(source, world.player)
    target_region = world.multiworld.get_region(target, world.player)

    if target not in used_names:
        used_names[target] = 1
        name = target
    else:
        used_names[target] += 1
        name = target + (' ' * used_names[target])

    connection = Entrance(world.player, name, source_region)

    if rule:
        connection.access_rule = rule

    source_region.exits.append(connection)
    connection.connect(target_region)
