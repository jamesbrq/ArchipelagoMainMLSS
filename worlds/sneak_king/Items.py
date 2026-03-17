from BaseClasses import ItemClassification, Item


class ItemData():
    def __init__(self, name: str, id: int, classification: ItemClassification, frequency: int = 1):
        self.name = name
        self.id = id
        self.classification = classification
        self.frequency = frequency


class SneakKingItem(Item):
    game = "Sneak King"


items = []
index = 0
for level in ["Sawmill", "Cul-De-Sac", "Construction", "Downtown"]:
    items += [ItemData(f"{level} Mission {i} Unlock", i + index, ItemClassification.progression) for i in range(1, 21)]
items += [
    ItemData("Sawmill Unlock", 81, ItemClassification.progression),
    ItemData("Cul-De-Sac", 82, ItemClassification.progression),
    ItemData("Construction Unlock", 83, ItemClassification.progression),
    ItemData("Downtown Unlock", 84, ItemClassification.progression),
    ItemData("Progressive Flourish", 85, ItemClassification.progression, 2),
    ItemData("Progressive Score Multiplier", 86, ItemClassification.progression),
]