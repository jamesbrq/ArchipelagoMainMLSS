import typing

if typing.TYPE_CHECKING:
    from . import TTYDWorld


class Encounter:
    name: str
    enemy_count: int
    enemy_ids: list[int]

    def __init__(self, name: str, enemy_count: int, enemy_ids: list[str]):
        self.name = name
        self.enemy_count = enemy_count
        self.enemy_ids = [int(_id, 0) for _id in enemy_ids]

def parse_json_encounters() -> list[Encounter]:
    import json
    import pkgutil

    return (json.loads(pkgutil.get_data(__name__, "json/enemies.json").decode("utf-8"),
                       object_hook=lambda d: Encounter(**d)))

def randomize_encounters(world: "TTYDWorld", group_type: int = 0) -> None:
    if group_type == 0:
        groups = [ids.enemy_ids for ids in world.encounters]
        world.random.shuffle(groups)
    elif group_type == 1:
        enemies = [_id for encounter in world.encounters for _id in encounter.enemy_ids]
        world.random.shuffle(enemies)
        groups = [[enemies.pop() for _ in range(encounter.enemy_count)] for encounter in world.encounters]
        world.random.shuffle(groups)
    else:
        raise ValueError(f"Invalid group type: {group_type}")

    for encounter in world.encounters:
        encounter.enemy_ids = next(i for i in groups if len(i) == encounter.enemy_count)
        groups.remove(encounter.enemy_ids)
