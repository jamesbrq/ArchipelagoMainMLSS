import typing

from BaseClasses import ItemClassification, Item


class ItemData():
    def __init__(self, name: str, id: int, classification: ItemClassification, frequency: int = 1):
        self.name = name
        self.id = id
        self.classification = classification
        self.frequency = frequency


class SneakKingItem(Item):
    game = "Sneak King"


items: list[ItemData] = []
for level in ["Sawmill", "Cul-De-Sac", "Construction", "Downtown"]:
    items += [ItemData(f"{level} Mission {i} Unlock", i, ItemClassification.progression) for i in range(2, 21)]  # start at 2
items += [
    ItemData("Sawmill Unlock", 81, ItemClassification.progression),
    ItemData("Cul-De-Sac Unlock", 82, ItemClassification.progression),
    ItemData("Construction Unlock", 83, ItemClassification.progression),
    ItemData("Downtown Unlock", 84, ItemClassification.progression),
    ItemData("Progressive Flourish", 85, ItemClassification.progression, 3),
    ItemData("Progressive Chain", 86, ItemClassification.progression, 3),
    ItemData("Nothing", 87, ItemClassification.filler, 0),
]

item_table: typing.Dict[str, ItemData] = {item.name: item for item in items}
items_by_id: typing.Dict[int, ItemData] = {item.id: item for item in items}
