from BaseClasses import Location

class LocationData():
    def __init__(self, name: str, id: int, tags: list[str]):
        self.name = name
        self.id = id
        self.tags = tags

all_locations: list[LocationData] = []
index = 0
for level in ["Sawmill", "Cul-De-Sac", "Construction", "Downtown"]:
    for rank in ["C", "B", "A"]:
        all_locations += [LocationData(f"{level}: Mission {i} Rank {rank}", index + i, [level, rank]) for i in range(1, 21)]
        index += 20


def get_locations_by_tag(tag: str):
    return [location for location in all_locations if tag in location.tags]

class SneakKingLocation(Location):
    game = "Sneak King"