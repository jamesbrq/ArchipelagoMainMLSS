from worlds.sneak_king.Locations import get_locations_by_tag

def create_regions(world: "SneakKingWorld")


def get_regions_dict():
    return {
        "Sawmill": get_locations_by_tag("Sawmill"),
        "Cul-De-Sac": get_locations_by_tag("Cul-De-Sac"),
        "Construction": get_locations_by_tag("Construction"),
        "Downtown": get_locations_by_tag("Downtown")
    }