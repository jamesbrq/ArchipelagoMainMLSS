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
        all_locations += [LocationData(f"{level}: Mission {i} Rank {rank}", index + i, [level, rank, "mission"]) for i in range(1, 21)]
        index += 20

interactable_objects: dict[str, list[tuple[str, str]]] = {
    "Sawmill": [
        ("1A_Int_Door01", "Door 1"),
        ("1A_Int_Door02", "Door 2"),
        ("1A_Int_Door03", "Door 3"),
        ("1A_Int_Door04", "Door 4"),
        ("1A_Int_Door05", "Door 5"),
        ("1A_Int_Door06", "Door 6"),
        ("1A_Int_HP001", "Hollow Log 1"),
        ("1A_Int_HP002", "Hollow Log 2"),
        ("1A_Int_HP003", "Large Crate 1"),
        ("1A_Int_HP004", "Large Crate 2"),
        ("1A_Int_HP005", "Large Crate 3"),
        ("1A_Int_HP006", "Hollow Log 3"),
        ("1A_Int_HP007", "Hollow Log 4"),
        ("1A_Int_HP008", "Crate in Truck Bed 1"),
        ("1A_Int_HP009", "Crate in Truck Bed 2"),
        ("1A_Int_HP010", "Hollow Log 5"),
        ("1A_Int_HP011", "Hollow Log 6"),
        ("1A_Int_HP012", "Crate in Truck Bed 3"),
        ("1A_Int_HP013", "Crate in Truck Bed 4"),
        ("1A_Int_HP014", "Large Crate 4"),
        ("1A_Int_HP015", "Large Crate 5"),
        ("1A_Int_HP016", "Large Crate 6"),
        ("1A_Int_HP017", "Green Barrel 1"),
        ("1A_Int_HP018", "Green Barrel 2"),
        ("1A_Int_HP019", "Pile of Leaves 1"),
        ("1A_Int_HP020", "Pile of Leaves 2"),
        ("1A_Int_HP021", "Pile of Leaves 3"),
        ("1A_Int_HP022", "Pile of Leaves 4"),
        ("1A_Int_HP023", "Pile of Leaves 5"),
        ("1A_Int_HP024", "Pile of Leaves 6"),
        ("1A_Int_HP025", "Pile of Leaves 7"),
        ("1A_Int_HP026", "Green Barrel 3"),
        ("1A_Int_HP027", "Under Truck 1"),
        ("1A_Int_HP028", "Under Truck 2"),
        ("1A_Int_HP030", "Green Barrel 4"),
        ("1A_Int_HP031", "Green Barrel 5"),
        ("1A_Int_HP032", "Green Barrel 6"),
        ("1A_Int_HP033", "Green Barrel 7"),
        ("1A_Int_HP034", "Crate 1"),
        ("1A_Int_HP035", "Crate 2"),
        ("1A_Int_HP036", "Crate 3"),
        ("1A_Int_HP037", "Crate 4"),
        ("1A_Int_HP038", "Crate 5"),
        ("1A_Int_HP039", "Crate 6"),
        ("1A_Int_HP040", "Pile of Leaves 8"),
        ("1A_Int_HP041", "Pile of Leaves 9"),
        ("1A_Int_Ladder01", "Ladder"),
        ("1A_Int_Portaloo01", "Porta-Potty"),
        ("1A_Int_Shortcut01", "Shortcut 1"),
        ("1A_Int_Shortcut02", "Shortcut 2"),
        ("1A_Int_Tree01", "Tree 1"),
        ("1A_Int_Tree02", "Tree 2"),
        ("1PA_Int_BridgePanel01", "Bridge Panel"),
    ],
    "Cul-De-Sac": [
        ("2A_Bin 001", "Trash Can 1"),
        ("2A_Bin 002", "Trash Can 2"),
        ("2A_Bin 003", "Trash Can 3"),
        ("2A_Bin 004", "Trash Can 4"),
        ("2A_Bin 005", "Trash Can 5"),
        ("2A_Bin 006", "Trash Can 6"),
        ("2A_Bin 008", "Trash Can 7"),
        ("2A_Bin 009", "Trash Can 8"),
        ("2A_Bin 010", "Trash Can 9"),
        ("2A_Bin 011", "Trash Can 10"),
        ("2A_Bin 013", "Trash Can 11"),
        ("2A_Bin 015", "Trash Can 12"),
        ("2A_Bin1", "Trash Can 13"),
        ("2A_Int_Door 001", "Door 1"),
        ("2A_Int_Door 002", "Door 2"),
        ("2A_Int_Door 003", "Door 3"),
        ("2A_Int_Door 004", "Door 4"),
        ("2A_Int_Door 005", "Door 5"),
        ("2A_Int_Door 006", "Door 6"),
        ("2A_Int_Door 007", "Door 7"),
        ("2A_Int_Door 008", "Door 8"),
        ("2A_Int_Door 009", "Door 9"),
        ("2A_Int_Door 010", "Door 10"),
        ("2A_Int_Door 011", "Door 11"),
        ("2A_Int_Door 013", "Door 12"),
        ("2A_Int_Door 014", "Door 13"),
        ("2A_Int_Door 015", "Door 14"),
        ("2A_Mailbox 002", "Knock on Window"),
        ("2A_crate 001", "Crate 1"),
        ("2A_crate 002", "Crate 2"),
        ("2A_treehouse 001", "Treehouse"),
    ],
    "Construction": [
        ("3A_Barrel01", "Barrel 1"),
        ("3A_Barrel02", "Barrel 2"),
        ("3A_Barrel03", "Barrel 3"),
        ("3A_Barrel04", "Barrel 4"),
        ("3A_Barrel05", "Barrel 5"),
        ("3A_Barrel06", "Barrel 6"),
        ("3A_Barrel07", "Barrel 7"),
        ("3A_Crate01", "Crate 1"),
        ("3A_Crate02", "Crate 2"),
        ("3A_Crate03", "Crate 3"),
        ("3A_Crate04", "Crate 4"),
        ("3A_Crate05", "Crate 5"),
        ("3A_Crate06", "Crate 6"),
        ("3A_Crate07", "Crate 7"),
        ("3A_DiggerScoop", "Raised Truck Scoop"),
        ("3A_Door01", "Door 1"),
        ("3A_Door02_knocker", "Knock on Door 2"),
        ("3A_Door03_knocker", "Knock on Door 3"),
        ("3A_Door_Portaloo", "Porta-Potty"),
        ("3A_LadderBase", "Ladder"),
        ("3A_Manhole1", "Manhole 1"),
        ("3A_Manhole2", "Manhole 2"),
        ("3A_PipeEnd02", "Container 1"),
        ("3A_PipeEnd04", "Container 2"),
        ("3A_PipeEndRaised1", "Raised Container"),
        ("3A_PipeFlat", "Pipe Roll"),
        ("3A_PipeRamp", "Pipe Ramp"),
        ("3A_PipeV", "Vertical Pipe"),
        ("3A_Sandpile", "Sand Pile"),
        ("3A_Skip1", "Dumpster 1"),
        ("3A_Skip2", "Dumpster 2"),
    ],
    "Downtown": [
        ("4A_HP 001", "Trash Can 1"),
        ("4A_HP 003", "Trash Can 2"),
        ("4A_HP 004", "Dumpster 1"),
        ("4A_HP 006", "Trash Can 3"),
        ("4A_HP 007", "Green Barrel 1"),
        ("4A_HP 008", "Crate 1"),
        ("4A_HP 009", "Trash Can 4"),
        ("4A_HP 010", "Green Barrel 2"),
        ("4A_HP 014", "Trash Can 5"),
        ("4A_HP 015", "Dumpster 2"),
        ("4A_HP 017", "Green Barrel 3"),
        ("4A_HP 019", "Crate 2"),
        ("4A_HP 022", "Trash Can 6"),
        ("4A_HP 023", "Dumpster 3"),
        ("4A_HP 025", "Crate 3"),
        ("4A_HP 027", "Trash Can 7"),
        ("4A_HPskip 001", "Dumpster 4"),
        ("4A_Int_SC03", "Sewer Entrance 1"),
        ("4A_Int_SC04", "Sewer Entrance 2"),
        ("4A_SceneryProp_Car 006", "Crate in Truck Bed"),
        ("4A_Subway1_entrance", "Subway 1 Entrance"),
        ("4A_Subway2_entrance", "Subway 2 Entrance"),
        ("4A_Telemaphone_door", "Phone Booth 1"),
        ("4A_Telemaphone_door2", "Phone Booth 2"),
    ],
}

index += 1

for level, objects in interactable_objects.items():
    for entity_name, display_name in objects:
        all_locations.append(LocationData(
            f"{level}: {display_name}",
            index,
            [level, "interactable"]
        ))
        index += 1


def get_locations_by_tag(tag: str):
    return [location for location in all_locations if tag in location.tags]

class SneakKingLocation(Location):
    game = "Sneak King"
