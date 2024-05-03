import typing

from BaseClasses import Item, ItemClassification


class ItemData(typing.NamedTuple):
    code: int
    itemName: str
    classification: ItemClassification


class MLSSItem(Item):
    game: str = "Sonic Adventure DX"


itemList: typing.List[ItemData] = [
    ItemData(77871000, "Sonic - Light-Speed Shoes", ItemClassification.progression),
    ItemData(77871001, "Sonic - Crystal Ring", ItemClassification.useful),
    ItemData(77871002, "Sonic - Ancient Light", ItemClassification.progression),
    ItemData(77871003, "Tails - Jet Anklet", ItemClassification.useful),
    ItemData(77871004, "Tails - Rhythm Badge", ItemClassification.useful),
    ItemData(77871005, "Knuckles - Shovel Claws", ItemClassification.progression),
    ItemData(77871006, "Knuckles - Fighting Gloves", ItemClassification.useful),
    ItemData(77871007, "Amy - Warrior Feather", ItemClassification.useful),
    ItemData(77871008, "Amy - Long Hammer", ItemClassification.useful),
    ItemData(77871009, "Big - Life Belt", ItemClassification.progression),
    ItemData(77871010, "Big - Power Rod", ItemClassification.useful),
    ItemData(77871011, "Big - Progressive Lure Upgrade", ItemClassification.useful),
    ItemData(77871012, "Gamma - Jet Booster", ItemClassification.progression),
    ItemData(77871013, "Gamma - Laser Blaster", ItemClassification.useful),
    ItemData(77871014, "Sonic - Wind Stone", ItemClassification.progression),
    ItemData(77871015, "Tails - Wind Stone", ItemClassification.progression),
    ItemData(77871016, "Gamma - Wind Stone", ItemClassification.progression),
    ItemData(77871017, "Sonic - Ice Stone", ItemClassification.progression),
    ItemData(77871018, "Tails - Ice Stone", ItemClassification.progression),
    ItemData(77871019, "Big - Ice Stone", ItemClassification.progression),
    ItemData(77871020, "Knuckles - Gold Statue", ItemClassification.filler),
    ItemData(77871021, "Knuckles - Silver Statue", ItemClassification.filler),
    ItemData(77871022, "Emblem", ItemClassification.progression),
    ItemData(77871023, "5 Rings", ItemClassification.filler),
    ItemData(77871024, "10 Rings", ItemClassification.filler),
    ItemData(77871025, "Extra Life", ItemClassification.filler),
    ItemData(77871026, "Magnet", ItemClassification.filler),
    ItemData(77871027, "Shield", ItemClassification.filler),
    ItemData(77871028, "Invincibility", ItemClassification.filler),
    ItemData(77871029, "Speed Up", ItemClassification.filler),
    ItemData(77871030, "Sonic", ItemClassification.filler),
    ItemData(77871031, "Tails", ItemClassification.filler),
    ItemData(77871032, "Knuckles", ItemClassification.filler),
    ItemData(77871033, "Amy", ItemClassification.filler),
    ItemData(77871034, "Big", ItemClassification.filler),
    ItemData(77871035, "Gamma", ItemClassification.filler),
]

item_frequencies: typing.Dict[str, int] = {
    "5 Coins": 40,
    "Mushroom": 55,
    "Super Mushroom": 15,
    "Ultra Mushroom": 12,
    "Nuts": 10,
    "Super Nuts": 5,
    "Ultra Nuts": 5,
    "Max Nuts": 2,
    "Syrup": 28,
    "Super Syrup": 10,
    "Ultra Syrup": 10,
    "Max Syrup": 2,
    "1-Up Mushroom": 15,
    "1-Up Super": 5,
    "Golden Mushroom": 3,
    "Refreshing Herb": 9,
    "Red Pepper": 2,
    "Green Pepper": 2,
    "Hoo Bean": 100,
    "Chuckle Bean": 200,
    "Hammers": 3
}

item_table: typing.Dict[str, ItemData] = {item.itemName: item for item in itemList}
items_by_id: typing.Dict[int, ItemData] = {item.code: item for item in itemList}
