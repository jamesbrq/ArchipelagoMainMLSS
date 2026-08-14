from collections.abc import Mapping
from types import MappingProxyType
from typing import Final

from BaseClasses import Item, ItemClassification


class ItemData:
    id: int
    item_name: str
    progression: ItemClassification
    frequency: int
    grant: str
    rom_id: int

    def __init__(self, id: int | None = 0, item_name: str = "", progression: int = 0, frequency: int = 1, grant: str = "none", rom_id: str = "0x0", note: str = "", door: str = ""):
        self.id = id
        self.item_name = item_name
        self.progression = ItemClassification(progression)
        self.frequency = frequency
        self.grant = grant
        self.rom_id = int(rom_id, 16)
        self.note = note
        # Only per-door keys carry this: the door id from json/rules.json this key
        # opens. Empty for every other item.
        self.door = door


class MickeyItem(Item):
    game: str = "Disney's Magical Mirror"


def _load(path: str) -> list[dict]:
    import orjson
    import pkgutil

    return orjson.loads(pkgutil.get_data(__name__, path).decode("utf-8"))


def import_items() -> tuple[ItemData, ...]:
    return tuple(ItemData(**item) for item in _load("json/items.json"))


def import_door_keys() -> tuple[ItemData, ...]:
    """The per-door keys, one per lockable door, for `key_mode: per_door`.

    A separate file from items.json because a different generator owns it: the door
    registry is built by tools/gen_ap_rules.py, while gen_ap_data.py stays the one
    authority for the base items. They use disjoint id ranges, and a per-door key's
    id is keyed to its door, so renaming a room changes the item's NAME but never
    its id.

    Every lockable door has a key defined whether or not this seed locks it --
    item_name_to_id has to be the same table for every player.
    """
    return tuple(ItemData(**row) for row in _load("json/door_keys.json"))


base_item_list: Final[tuple[ItemData, ...]] = import_items()
door_key_list: Final[tuple[ItemData, ...]] = import_door_keys()
item_list: Final[tuple[ItemData, ...]] = base_item_list + door_key_list

door_keys: Final[Mapping[str, str]] = MappingProxyType(
    {item.door: item.item_name for item in door_key_list})
item_table: Final[Mapping[str, ItemData]] = MappingProxyType({item.item_name: item for item in item_list})
items_by_id: Final[Mapping[int, ItemData]] = MappingProxyType({item.id: item for item in item_list})


def items_by_grant(grant: str) -> tuple[ItemData, ...]:
    return tuple(item for item in item_list if item.grant == grant)


tricks: Final[tuple[str, ...]] = tuple(item.item_name for item in items_by_grant("ap_flag"))
quest_items: Final[tuple[str, ...]] = tuple(item.item_name for item in items_by_grant("inventory"))
collectibles: Final[tuple[str, ...]] = tuple(item.item_name for item in items_by_grant("flag"))

# `collectibles` is deliberately NOT a group: souvenirs and hats are locations only,
# never placed, so a group naming them could never match anything a player received.
mickey_item_name_groups: Final[Mapping[str, tuple[str, ...]]] = MappingProxyType({
    "Trick": tricks,
    "Quest Item": quest_items,
    "Key": ("Small Key",) + tuple(item.item_name for item in door_key_list),
})
