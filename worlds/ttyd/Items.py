import typing

from BaseClasses import Item, ItemClassification


class ItemData:
    code: int
    itemName: str
    progression: ItemClassification
    rom_id: int = 0x0

    def __init__(self, code: int, itemName: str, progression: ItemClassification, rom_id: int = 0x0):
        self.code = code
        self.itemName = itemName
        self.progression = progression
        self.rom_id = rom_id


class TTYDItem(Item):
    game: str = "Paper Mario: The Thousand Year Door"


itemList: typing.List[ItemData] = [
    ItemData(77772000, "10 Coins", ItemClassification.filler),
    ItemData(77772002, "All or Nothing", ItemClassification.useful),
    ItemData(77772003, "Attack FX G", ItemClassification.useful),
    ItemData(77772004, "Attack FX P", ItemClassification.useful),
    ItemData(77772005, "Attack FX R", ItemClassification.useful),
    ItemData(77772006, "Attack FX Y", ItemClassification.useful),
    ItemData(77772007, "Autograph", ItemClassification.progression),
    ItemData(77772008, "Black Key 1", ItemClassification.progression),
    ItemData(77772009, "Black Key 2", ItemClassification.progression),
    ItemData(77772010, "Black Key 3", ItemClassification.progression),
    ItemData(77772011, "Black Key 4", ItemClassification.progression),
    ItemData(77772012, "Blanket", ItemClassification.progression),
    ItemData(77772013, "Blimp Ticket", ItemClassification.progression),
    ItemData(77772014, "Blue Key", ItemClassification.progression),
    ItemData(77772015, "Boat Curse", ItemClassification.progression),
    ItemData(77772016, "Bobbery", ItemClassification.progression),
    ItemData(77772017, "Boo's Sheet", ItemClassification.useful,),
    ItemData(77772018, "Briefcase", ItemClassification.progression),
    ItemData(77772019, "Bump Attack", ItemClassification.filler),
    ItemData(77772020, "Cake Mix", ItemClassification.filler),
    ItemData(77772021, "Card Key 1", ItemClassification.progression),
    ItemData(77772022, "Card Key 2", ItemClassification.progression),
    ItemData(77772023, "Card Key 3", ItemClassification.progression),
    ItemData(77772024, "Card Key 4", ItemClassification.progression),
    ItemData(77772025, "Castle Key 1", ItemClassification.progression),
    ItemData(77772219, "Castle Key 2", ItemClassification.progression),
    ItemData(77772220, "Castle Key 3", ItemClassification.progression),
    ItemData(77772221, "Castle Key 4", ItemClassification.progression),
    ItemData(77772026, "Champ's Belt", ItemClassification.progression),
    ItemData(77772027, "Charge", ItemClassification.useful),
    ItemData(77772028, "Charge P", ItemClassification.useful),
    ItemData(77772029, "Chill Out", ItemClassification.useful),
    ItemData(77772030, "Chuckola Cola", ItemClassification.progression),
    ItemData(77772031, "Close Call", ItemClassification.useful),
    ItemData(77772032, "Close Call P", ItemClassification.useful),
    ItemData(77772033, "Coconut", ItemClassification.progression),
    ItemData(77772034, "Cog", ItemClassification.progression),
    ItemData(77772035, "Coin", ItemClassification.filler),
    ItemData(77772036, "Contact Lens", ItemClassification.progression),
    ItemData(77772037, "Cookbook", ItemClassification.progression),
    ItemData(77772038, "Courage Shell", ItemClassification.filler),
    ItemData(77772039, "Crystal Star", ItemClassification.progression),
    ItemData(77772040, "Damage Dodge", ItemClassification.progression),
    ItemData(77772041, "Damage Dodge P", ItemClassification.progression),
    ItemData(77772042, "Defend Plus", ItemClassification.progression),
    ItemData(77772043, "Defend Plus P", ItemClassification.progression),
    ItemData(77772044, "Diamond Star", ItemClassification.progression),
    ItemData(77772045, "Dizzy Dial", ItemClassification.filler),
    ItemData(77772046, "Double Dip", ItemClassification.useful),
    ItemData(77772047, "Double Dip P", ItemClassification.useful),
    ItemData(77772048, "Double Pain", ItemClassification.useful),
    ItemData(77772049, "Dried Shroom", ItemClassification.filler),
    ItemData(77772050, "Dubious Paper", ItemClassification.progression),
    ItemData(77772051, "Earth Quake", ItemClassification.filler),
    ItemData(77772052, "Elevator Key", ItemClassification.progression),
    ItemData(77772053, "Elevator Key 1", ItemClassification.progression),
    ItemData(77772054, "Elevator Key 2", ItemClassification.progression),
    ItemData(77772055, "Emerald Star", ItemClassification.progression),
    ItemData(77772056, "Feeling Fine", ItemClassification.useful),
    ItemData(77772057, "Feeling Fine P", ItemClassification.useful),
    ItemData(77772058, "Fire Drive", ItemClassification.useful),
    ItemData(77772059, "Fire Flower", ItemClassification.filler),
    ItemData(77772060, "First Attack", ItemClassification.useful),
    ItemData(77772061, "Flower Finder", ItemClassification.useful),
    ItemData(77772062, "Flower Saver", ItemClassification.useful),
    ItemData(77772063, "Flower Saver P", ItemClassification.useful),
    ItemData(77772064, "Flurrie", ItemClassification.progression),
    ItemData(77772065, "FP Drain", ItemClassification.useful),
    ItemData(77772066, "FP Plus", ItemClassification.useful),
    ItemData(77772067, "Fresh Pasta", ItemClassification.filler),
    ItemData(77772068, "Fright Mask", ItemClassification.filler),
    ItemData(77772069, "Galley Pot", ItemClassification.progression),
    ItemData(77772070, "Garnet Star", ItemClassification.progression),
    ItemData(77772071, "Gate Handle", ItemClassification.progression),
    ItemData(77772072, "Gold Bar", ItemClassification.useful),
    ItemData(77772073, "Gold Bar x3", ItemClassification.useful),
    ItemData(77772074, "Gold Ring", ItemClassification.progression),
    ItemData(77772075, "Gold Star", ItemClassification.progression),
    ItemData(77772076, "Goldbob Guide", ItemClassification.progression),
    ItemData(77772077, "Golden Leaf", ItemClassification.filler),
    ItemData(77772078, "Goombella", ItemClassification.progression),
    ItemData(77772079, "Gradual Syrup", ItemClassification.filler),
    ItemData(77772080, "Grotto Key", ItemClassification.progression),
    ItemData(77772081, "Hammer Throw", ItemClassification.useful),
    ItemData(77772082, "Hammerman", ItemClassification.useful),
    ItemData(77772083, "Happy Flower", ItemClassification.useful),
    ItemData(77772084, "Happy Heart", ItemClassification.useful),
    ItemData(77772085, "Happy Heart P", ItemClassification.useful),
    ItemData(77772086, "Head Rattle", ItemClassification.useful),
    ItemData(77772087, "Heart Finder", ItemClassification.useful),
    ItemData(77772088, "Honey Syrup", ItemClassification.filler),
    ItemData(77772089, "Horsetail", ItemClassification.filler),
    ItemData(77772090, "Hot Dog", ItemClassification.filler),
    ItemData(77772091, "HP Drain", ItemClassification.filler),
    ItemData(77772092, "HP Drain (Badge)", ItemClassification.useful),
    ItemData(77772093, "HP Drain P", ItemClassification.useful),
    ItemData(77772094, "HP Plus", ItemClassification.useful),
    ItemData(77772095, "HP Plus P", ItemClassification.useful),
    ItemData(77772096, "Ice Power", ItemClassification.useful),
    ItemData(77772097, "Ice Smash", ItemClassification.useful),
    ItemData(77772098, "Ice Storm", ItemClassification.filler),
    ItemData(77772099, "Inn Coupon", ItemClassification.filler),
    ItemData(77772100, "Item Hog", ItemClassification.useful),
    ItemData(77772101, "Jammin' Jelly", ItemClassification.useful),
    ItemData(77772102, "Jumpman", ItemClassification.useful),
    ItemData(77772103, "Keel Mango", ItemClassification.filler),
    ItemData(77772104, "Koops", ItemClassification.progression),
    ItemData(77772105, "L Emblem", ItemClassification.useful),
    ItemData(77772106, "Last Stand", ItemClassification.useful),
    ItemData(77772107, "Last Stand P", ItemClassification.useful),
    ItemData(77772108, "Life Shroom", ItemClassification.useful),
    ItemData(77772109, "Lottery Pick", ItemClassification.useful),
    ItemData(77772110, "Lucky Day", ItemClassification.useful),
    ItemData(77772111, "Lucky Start", ItemClassification.useful),
    ItemData(77772112, "Maple Syrup", ItemClassification.filler),
    ItemData(77772113, "Mega Rush", ItemClassification.useful),
    ItemData(77772114, "Mega Rush P", ItemClassification.useful),
    ItemData(77772115, "Mini Mr.Mini", ItemClassification.filler),
    ItemData(77772116, "Money Money", ItemClassification.useful),
    ItemData(77772117, "Moon Stone", ItemClassification.progression),
    ItemData(77772118, "Mr. Softener", ItemClassification.filler),
    ItemData(77772119, "Multibounce", ItemClassification.useful),
    ItemData(77772120, "Mushroom", ItemClassification.filler),
    ItemData(77772121, "Mystery", ItemClassification.filler),
    ItemData(77772122, "Mystic Egg", ItemClassification.filler),
    ItemData(77772123, "Necklace", ItemClassification.progression),
    ItemData(77772124, "Old Letter", ItemClassification.progression),
    ItemData(77772125, "Omelette Meal", ItemClassification.filler),
    ItemData(77772126, "P-Down D-Up", ItemClassification.useful),
    ItemData(77772127, "P-Down D-Up P", ItemClassification.useful),
    ItemData(77772128, "P-Up D-Down", ItemClassification.useful),
    ItemData(77772129, "P-Up D-Down P", ItemClassification.useful),
    ItemData(77772130, "Palace Key", ItemClassification.progression),
    ItemData(77772131, "Palace Key (Riddle Tower)", ItemClassification.progression),
    ItemData(77772132, "Paper Curse", ItemClassification.progression),
    ItemData(77772133, "Peachy Peach", ItemClassification.filler),
    ItemData(77772134, "Peekaboo", ItemClassification.useful),
    ItemData(77772135, "Piercing Blow", ItemClassification.useful),
    ItemData(77772136, "Pity Flower", ItemClassification.useful),
    ItemData(77772137, "Plane Curse", ItemClassification.progression),
    ItemData(77772138, "Point Swap", ItemClassification.filler),
    ItemData(77772139, "POW Block", ItemClassification.filler),
    ItemData(77772140, "Power Bounce", ItemClassification.useful),
    ItemData(77772141, "Power Jump", ItemClassification.useful),
    ItemData(77772142, "Power Plus", ItemClassification.useful),
    ItemData(77772143, "Power Plus P", ItemClassification.useful),
    ItemData(77772144, "Power Punch", ItemClassification.filler),
    ItemData(77772145, "Power Rush", ItemClassification.useful),
    ItemData(77772146, "Power Rush P", ItemClassification.useful),
    ItemData(77772147, "Power Smash", ItemClassification.useful),
    ItemData(77772148, "Pretty Lucky", ItemClassification.useful),
    ItemData(77772149, "Pretty Lucky P", ItemClassification.useful),
    ItemData(77772150, "Puni Orb", ItemClassification.progression),
    ItemData(77772151, "Quake Hammer", ItemClassification.useful),
    ItemData(77772152, "Quick Change", ItemClassification.useful),
    ItemData(77772153, "Ragged Diary", ItemClassification.progression),
    ItemData(77772154, "Red Key", ItemClassification.progression),
    ItemData(77772155, "Refund", ItemClassification.useful),
    ItemData(77772156, "Repel Cape", ItemClassification.filler),
    ItemData(77772157, "Return Postage", ItemClassification.useful),
    ItemData(77772158, "Ruby Star", ItemClassification.progression),
    ItemData(77772159, "Ruin Powder", ItemClassification.filler),
    ItemData(77772160, "Sapphire Star", ItemClassification.progression),
    ItemData(77772161, "Shell Earrings", ItemClassification.progression),
    ItemData(77772162, "Shine Sprite", ItemClassification.useful),
    ItemData(77772164, "Shooting Star", ItemClassification.useful),
    ItemData(77772165, "Shop Key", ItemClassification.progression),
    ItemData(77772166, "Shrink Stomp", ItemClassification.useful),
    ItemData(77772167, "Simplifier", ItemClassification.useful),
    ItemData(77772168, "Skull Gem", ItemClassification.progression),
    ItemData(77772169, "Sleepy Sheep", ItemClassification.filler),
    ItemData(77772170, "Slow Go", ItemClassification.useful),
    ItemData(77772171, "Slow Shroom", ItemClassification.filler),
    ItemData(77772172, "Soft Stomp", ItemClassification.useful),
    ItemData(77772173, "Space Food", ItemClassification.filler),
    ItemData(77772174, "Spike Shield", ItemClassification.useful),
    ItemData(77772175, "Spite Pouch", ItemClassification.filler),
    ItemData(77772176, "Star Key", ItemClassification.progression),
    ItemData(77772177, "Star Piece", ItemClassification.progression),
    ItemData(77772178, "Station Key 1", ItemClassification.progression),
    ItemData(77772179, "Station Key 2", ItemClassification.progression),
    ItemData(77772180, "Steeple Key 1", ItemClassification.progression),
    ItemData(77772181, "Steeple Key 2", ItemClassification.progression),
    ItemData(77772182, "Stopwatch", ItemClassification.filler),
    ItemData(77772183, "Storage Key 1", ItemClassification.progression),
    ItemData(77772184, "Storage Key 2", ItemClassification.progression),
    ItemData(77772185, "Strange Sack", ItemClassification.useful),
    ItemData(77772186, "Sun Stone", ItemClassification.progression),
    ItemData(77772187, "Super Appeal", ItemClassification.useful),
    ItemData(77772188, "Super Appeal P", ItemClassification.useful),
    ItemData(77772190, "Progressive Hammer", ItemClassification.progression),
    ItemData(77772191, "Super Shroom", ItemClassification.filler),
    ItemData(77772192, "Superbombomb", ItemClassification.progression),
    ItemData(77772193, "Tasty Tonic", ItemClassification.filler),
    ItemData(77772194, "The Letter \"P\"", ItemClassification.progression),
    ItemData(77772195, "Thunder Bolt", ItemClassification.filler),
    ItemData(77772196, "Thunder Rage", ItemClassification.useful),
    ItemData(77772197, "Timing Tutor", ItemClassification.useful),
    ItemData(77772198, "Tornado Jump", ItemClassification.useful),
    ItemData(77772199, "Train Ticket", ItemClassification.progression),
    ItemData(77772200, "Tube Curse", ItemClassification.progression),
    ItemData(77772201, "Turtley Leaf", ItemClassification.filler),
    ItemData(77772202, "Progressive Boots", ItemClassification.progression),
    ItemData(77772204, "Ultra Shroom", ItemClassification.useful),
    ItemData(77772205, "Unsimplifier", ItemClassification.useful),
    ItemData(77772206, "Up Arrow", ItemClassification.useful),
    ItemData(77772207, "Vital Paper", ItemClassification.progression),
    ItemData(77772208, "Vivian", ItemClassification.progression),
    ItemData(77772209, "Volt Shroom", ItemClassification.filler),
    ItemData(77772210, "W Emblem", ItemClassification.useful),
    ItemData(77772211, "Wedding Ring", ItemClassification.progression),
    ItemData(77772212, "Whacka Bump", ItemClassification.filler),
    ItemData(77772213, "Yoshi", ItemClassification.progression),
    ItemData(77772214, "Zap Tap", ItemClassification.useful),
    ItemData(77772215, "Silver Card", ItemClassification.progression),
    ItemData(77772216, "Gold Card", ItemClassification.progression),
    ItemData(77772217, "Platinum Card", ItemClassification.progression),
    ItemData(77772218, "Special Card", ItemClassification.progression),
]

item_frequencies: typing.Dict[str, int] = {
    "10 Coins": 10,
    "Boo's Sheet": 4,
    "Castle Key": 4,
    "Close Call": 2,
    "Close Call P": 2,
    "Coconut": 2,
    "Coin": 30,
    "Courage Shell": 3,
    "Damage Dodge": 2,
    "Damage Dodge P": 2,
    "Defend Plus": 2,
    "Defend Plus P": 2,
    "Dizzy Dial": 2,
    "Double Dip": 2,
    "Double Dip P": 2,
    "Dried Shroom": 4,
    "Earth Quake": 3,
    "Fire Drive": 2,
    "Fire Flower": 10,
    "Flower Saver": 2,
    "Flower Saver P": 2,
    "FP Plus": 3,
    "Fright Mask": 2,
    "Gold Bar": 2,
    "Gold Bar x3": 3,
    "Gradual Syrup": 2,
    "Hammer Throw": 2,
    "Happy Flower": 2,
    "Happy Heart": 2,
    "Happy Heart P": 2,
    "Head Rattle": 2,
    "Honey Syrup": 7,
    "HP Drain": 2,
    "HP Plus": 3,
    "HP Plus P": 3,
    "Ice Smash": 2,
    "Ice Storm": 5,
    "Inn Coupon": 7,
    "Jammin' Jelly": 10,
    "Last Stand": 2,
    "Last Stand P": 2,
    "Life Shroom": 9,
    "Maple Syrup": 5,
    "Mini Mr.Mini": 2,
    "Mr.Softener": 2,
    "Multibounce": 2,
    "Mushroom": 13,
    "Mystery": 3,
    "Palace Key": 3,
    "Palace Key (Riddle Tower)": 8,
    "Point Swap": 2,
    "POW Block": 3,
    "Power Jump": 2,
    "Power Plus": 2,
    "Power Plus P": 2,
    "Power Punch": 3,
    "Power Rush": 2,
    "Power Rush P": 2,
    "Power Smash": 2,
    "Pretty Lucky": 2,
    "Quake Hammer": 2,
    "Repel Cape": 3,
    "Ruin Powder": 3,
    "Shine Sprite": 50,
    "Shooting Star": 8,
    "Shrink Stomp": 2,
    "Simplifier": 2,
    "Sleepy Sheep": 5,
    "Sleepy Stomp": 2,
    "Slow Shroom": 2,
    "Soft Stomp": 2,
    "Spite Pouch": 2,
    "Star Piece": 120,
    "Stopwatch": 5,
    "Super Appeal": 2,
    "Super Appeal P": 2,
    "Super Shroom": 15,
    "Tasty Tonic": 2,
    "Thunder Bolt": 2,
    "Thunder Rage": 8,
    "Tornado Jump": 2,
    "Ultra Mushroom": 15,
    "Unsimplifier": 2,
    "Volt Shroom": 2,
    "Whacka Bump": 8,
    "Diamond Star": 0,
    "Emerald Star": 0,
    "Gold Star": 0,
    "Ruby Star": 0,
    "Sapphire Star": 0,
    "Garnet Star": 0,
    "Crystal Star": 0,
    "Progressive Boots": 2,
    "Progressive Hammer": 2
}

item_type_dict = {
    "Invalid Item": 0x0,
    "Strange Sack": 0x1,
    "Paper Curse": 0x2,
    "Tube Curse": 0x3,
    "Plane Curse": 0x4,
    "Boat Curse": 0x5,
    "Progressive Boots": 0x6,
    "Super Boots": 0x7,
    "Ultra Boots": 0x8,
    "Progressive Hammer": 0x9,
    "Super Hammer": 0xA,
    "Ultra Hammer": 0xB,
    "Castle Key 1": 0xC,
    "Castle Key 2": 0xD,
    "Castle Key 3": 0xE,
    "Castle Key 4": 0xF,
    "Red Key": 0x10,
    "Blue Key": 0x11,
    "Storage Key 1": 0x12,
    "Storage Key 2": 0x13,
    "Grotto Key": 0x14,
    "Shop Key": 0x15,
    "Steeple Key 1": 0x16,
    "Steeple Key 2": 0x17,
    "Station Key 1": 0x18,
    "Station Key 2": 0x19,
    "Elevator Key": 0x1A,
    "Elevator Key 1": 0x1B,
    "Elevator Key 2": 0x1C,
    "Card Key 1": 0x1D,
    "Card Key 2": 0x1E,
    "Card Key 3": 0x1F,
    "Card Key 4": 0x20,
    "Black Key 1": 0x21,
    "Black Key 2": 0x22,
    "Black Key 3": 0x23,
    "Black Key 4": 0x24,
    "Star Key": 0x25,
    "Palace Key": 0x26,
    "Palace Key 2": 0x27,
    "Palace Key 3": 0x28,
    "Palace Key (Riddle Tower)": 0x29,
    "Palace Key (Riddle Tower) 2": 0x2A,
    "Palace Key (Riddle Tower) 3": 0x2B,
    "Palace Key (Riddle Tower) 4": 0x2C,
    "Palace Key (Riddle Tower) 5": 0x2D,
    "Palace Key (Riddle Tower) 6": 0x2E,
    "Palace Key (Riddle Tower) 7": 0x2F,
    "Palace Key (Riddle Tower) 8": 0x30,
    "House Key 0031": 0x31,
    "Magical Map": 0x32,
    "Contact Lens": 0x33,
    "Blimp Ticket": 0x34,
    "Train Ticket": 0x35,
    "Mailbox Sp": 0x36,
    "Goombella": 0x37,
    "Koops": 0x38,
    "Flurrie": 0x39,
    "Yoshi": 0x3A,
    "Vivian": 0x3B,
    "Cookbook": 0x3C,
    "Moon Stone": 0x3D,
    "Sun Stone": 0x3E,
    "Necklace": 0x3F,
    "Puni Orb": 0x40,
    "Champ's Belt": 0x41,
    "Poisoned Cake": 0x42,
    "Superbombomb": 0x43,
    "The Letter \"P\"": 0x44,
    "Old Letter": 0x45,
    "Chuckola Cola": 0x46,
    "Skull Gem": 0x47,
    "Gate Handle": 0x48,
    "Wedding Ring": 0x49,
    "Galley Pot": 0x4A,
    "Gold Ring": 0x4B,
    "Shell Earrings": 0x4C,
    "Autograph": 0x4D,
    "Ragged Diary": 0x4E,
    "Blanket": 0x4F,
    "Vital Paper": 0x50,
    "Briefcase": 0x51,
    "Goldbob Guide": 0x52,
    "10 Coins": 0x53,
    "Pog Invalid": 0x54,
    "Cog": 0x55,
    "Data Disk": 0x56,
    "Shine Sprite": 0x57,
    "Ultra Stone": 0x58,
    "Invalid Item Bowser Meat 0059": 0x59,
    "Invalid Item Mario Poster 005A": 0x5A,
    "Special Card": 0x5B,
    "Platinum Card": 0x5C,
    "Gold Card": 0x5D,
    "Silver Card": 0x5E,
    "Box": 0x5F,
    "Magical Map Large": 0x60,
    "Dubious Paper": 0x61,
    "Routing Slip": 0x62,
    "Wrestling Mag": 0x63,
    "Present": 0x64,
    "Blue Potion": 0x65,
    "Red Potion": 0x66,
    "Orange Potion": 0x67,
    "Green Potion": 0x68,
    "Invalid Item Star": 0x69,
    "Lottery Pick": 0x6A,
    "Battle Trunks": 0x6B,
    "Up Arrow": 0x6C,
    "Package": 0x6D,
    "Attack Fx B Key Item": 0x6E,
    "Bobbery": 0x6F,
    "Ms. Mowz": 0x70,
    "AP Item": 0x71,
    "Diamond Star": 0x72,
    "Emerald Star": 0x73,
    "Gold Star": 0x74,
    "Ruby Star": 0x75,
    "Sapphire Star": 0x76,
    "Garnet Star": 0x77,
    "Crystal Star": 0x78,
    "Coin": 0x79,
    "PiantA": 0x7A,
    "Heart Pickup": 0x7B,
    "Flower Pickup": 0x7C,
    "Star Piece": 0x7D,
    "Gold Bar": 0x7E,
    "Gold Bar x3": 0x7F,
    "Thunder Bolt": 0x80,
    "Thunder Rage": 0x81,
    "Shooting Star": 0x82,
    "Ice Storm": 0x83,
    "Fire Flower": 0x84,
    "Earth Quake": 0x85,
    "Boo's Sheet": 0x86,
    "Volt Shroom": 0x87,
    "Repel Cape": 0x88,
    "Ruin Powder": 0x89,
    "Sleepy Sheep": 0x8A,
    "POW Block": 0x8B,
    "Stopwatch": 0x8C,
    "Dizzy Dial": 0x8D,
    "Power Punch": 0x8E,
    "Courage Shell": 0x8F,
    "HP Drain": 0x90,
    "Trade Off": 0x91,
    "Mini Mr.Mini": 0x92,
    "Mr. Softener": 0x93,
    "Mushroom": 0x94,
    "Super Shroom": 0x95,
    "Ultra Shroom": 0x96,
    "Life Shroom": 0x97,
    "Dried Shroom": 0x98,
    "Tasty Tonic": 0x99,
    "Honey Syrup": 0x9A,
    "Maple Syrup": 0x9B,
    "Jammin' Jelly": 0x9C,
    "Slow Shroom": 0x9D,
    "Gradual Syrup": 0x9E,
    "Hot Dog": 0x9F,
    "Cake": 0xA0,
    "Point Swap": 0xA1,
    "Fright Mask": 0xA2,
    "Mystery": 0xA3,
    "Inn Coupon": 0xA4,
    "Whacka Bump": 0xA5,
    "Coconut": 0xA6,
    "Dried Bouquet": 0xA7,
    "Mystic Egg": 0xA8,
    "Golden Leaf": 0xA9,
    "Keel Mango": 0xAA,
    "Fresh Pasta": 0xAB,
    "Cake Mix": 0xAC,
    "Hot Sauce": 0xAD,
    "Turtley Leaf": 0xAE,
    "Horsetail": 0xAF,
    "Peachy Peach": 0xB0,
    "Spite Pouch": 0xB1,
    "Koopa Curse": 0xB2,
    "Shroom Fry": 0xB3,
    "Shroom Roast": 0xB4,
    "Shroom Steak": 0xB5,
    "Mistake": 0xB6,
    "Honey Shroom": 0xB7,
    "Maple Shroom": 0xB8,
    "Jelly Shroom": 0xB9,
    "Honey Super": 0xBA,
    "Maple Super": 0xBB,
    "Jelly Super": 0xBC,
    "Honey Ultra": 0xBD,
    "Maple Ultra": 0xBE,
    "Jelly Ultra": 0xBF,
    "Spicy Soup": 0xC0,
    "Zess Dinner": 0xC1,
    "Zess Special": 0xC2,
    "Zess Deluxe": 0xC3,
    "Zess Dynamite": 0xC4,
    "Zess Tea": 0xC5,
    "Space Food": 0xC6,
    "Icicle Pop": 0xC7,
    "Zess Frappe": 0xC8,
    "Snow Bunny": 0xC9,
    "Coconut Bomb": 0xCA,
    "Courage Meal": 0xCB,
    "Shroom Cake": 0xCC,
    "Shroom Crepe": 0xCD,
    "Mousse Cake": 0xCE,
    "Fried Egg": 0xCF,
    "Fruit Parfait": 0xD0,
    "Egg Bomb": 0xD1,
    "Ink Pasta": 0xD2,
    "Spaghetti": 0xD3,
    "Shroom Broth": 0xD4,
    "Poison Shroom": 0xD5,
    "Choco Cake": 0xD6,
    "Mango Delight": 0xD7,
    "Love Pudding": 0xD8,
    "Meteor Meal": 0xD9,
    "Trial Stew": 0xDA,
    "Couples Cake": 0xDB,
    "Inky Sauce": 0xDC,
    "Omelette Meal": 0xDD,
    "Koopa Tea": 0xDE,
    "Koopasta": 0xDF,
    "Spicy Pasta": 0xE0,
    "Heartful Cake": 0xE1,
    "Peach Tart": 0xE2,
    "Electro Pop": 0xE3,
    "Fire Pop": 0xE4,
    "Honey Candy": 0xE5,
    "Coco Candy": 0xE6,
    "Jelly Candy": 0xE7,
    "Zess Cookie": 0xE8,
    "Healthy Salad": 0xE9,
    "Koopa Bun": 0xEA,
    "Fresh Juice": 0xEB,
    "Audience Can": 0xEC,
    "Audience Rock": 0xED,
    "Audience Bone": 0xEE,
    "Audience Hammer": 0xEF,
    "Power Jump": 0xF0,
    "Multibounce": 0xF1,
    "Power Bounce": 0xF2,
    "Tornado Jump": 0xF3,
    "Shrink Stomp": 0xF4,
    "Sleepy Stomp": 0xF5,
    "Soft Stomp": 0xF6,
    "Power Smash": 0xF7,
    "Quake Hammer": 0xF8,
    "Hammer Throw": 0xF9,
    "Piercing Blow": 0xFA,
    "Head Rattle": 0xFB,
    "Fire Drive": 0xFC,
    "Ice Smash": 0xFD,
    "Double Dip": 0xFE,
    "Double Dip P": 0xFF,
    "Charge": 0x100,
    "Charge P": 0x101,
    "Super Appeal": 0x102,
    "Super Appeal P": 0x103,
    "Power Plus": 0x104,
    "Power Plus P": 0x105,
    "P-Up D-Down": 0x106,
    "P-Up D-Down P": 0x107,
    "All or Nothing": 0x108,
    "All or Nothing P": 0x109,
    "Mega Rush": 0x10A,
    "Mega Rush P": 0x10B,
    "Power Rush": 0x10C,
    "Power Rush P": 0x10D,
    "P-Down D-Up": 0x10E,
    "P-Down D-Up P": 0x10F,
    "Last Stand": 0x110,
    "Last Stand P": 0x111,
    "Defend Plus": 0x112,
    "Defend Plus P": 0x113,
    "Damage Dodge": 0x114,
    "Damage Dodge P": 0x115,
    "HP Plus": 0x116,
    "HP Plus P": 0x117,
    "FP Plus": 0x118,
    "Flower Saver": 0x119,
    "Flower Saver P": 0x11A,
    "Ice Power": 0x11B,
    "Spike Shield": 0x11C,
    "Feeling Fine": 0x11D,
    "Feeling Fine P": 0x11E,
    "Zap Tap": 0x11F,
    "Double Pain": 0x120,
    "Jumpman": 0x121,
    "Hammerman": 0x122,
    "Return Postage": 0x123,
    "Happy Heart": 0x124,
    "Happy Heart P": 0x125,
    "Happy Flower": 0x126,
    "HP Drain (Badge)": 0x127,
    "HP Drain P": 0x128,
    "FP Drain": 0x129,
    "FP Drain P": 0x12A,
    "Close Call": 0x12B,
    "Close Call P": 0x12C,
    "Pretty Lucky": 0x12D,
    "Pretty Lucky P": 0x12E,
    "Lucky Day": 0x12F,
    "Lucky Day P": 0x130,
    "Refund": 0x131,
    "Pity Flower": 0x132,
    "Pity Flower P": 0x133,
    "Quick Change": 0x134,
    "Peekaboo": 0x135,
    "Timing Tutor": 0x136,
    "Heart Finder": 0x137,
    "Flower Finder": 0x138,
    "Money Money": 0x139,
    "Item Hog": 0x13A,
    "Attack FX R": 0x13B,
    "Attack FX B": 0x13C,
    "Attack FX G": 0x13D,
    "Attack FX Y": 0x13E,
    "Attack FX P": 0x13F,
    "Chill Out": 0x140,
    "First Attack": 0x141,
    "Bump Attack": 0x142,
    "Slow Go": 0x143,
    "Simplifier": 0x144,
    "Unsimplifier": 0x145,
    "Lucky Start": 0x146,
    "L Emblem": 0x147,
    "W Emblem": 0x148,
    "Triple Dip": 0x149,
    "Lucky Start P": 0x14A,
    "Auto Command Badge": 0x14B,
    "Mega Jump": 0x14C,
    "Mega Smash": 0x14D,
    "Mega Quake": 0x14E,
    "Square Diamond Badge": 0x14F,
    "Square Diamond Badge P": 0x150,
    "Super Charge": 0x151,
    "Super Charge P": 0x152,
    "Max Item Type": 0x153
}

item_table: typing.Dict[str, ItemData] = {item.itemName: item for item in itemList}
items_by_id: typing.Dict[int, ItemData] = {item.code: item for item in itemList}
