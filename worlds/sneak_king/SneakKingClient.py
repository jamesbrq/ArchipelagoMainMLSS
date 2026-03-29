import asyncio
import re
import subprocess
import typing

import Patch
import Utils
import kvui
import settings
from CommonClient import ClientCommandProcessor, get_base_parser, gui_enabled, logger, server_loop
from NetUtils import ClientStatus

tracker_loaded = False
try:
    from worlds.tracker.TrackerClient import TrackerGameContext as cmmCtx, UT_VERSION
    tracker_loaded = True
except ModuleNotFoundError:
    from CommonClient import CommonContext as cmmCtx
    tracker_loaded = False

from .SneakKingMemory import SneakKingMemory, gid_to_group_slot, group_slot_to_gid
from .Locations import interactable_objects, all_locations

# ============================================================
# AP World <-> Game Memory Mapping
# ============================================================

# The AP world uses level names; the game uses group indices
LEVEL_NAMES = ["Sawmill", "Cul-De-Sac", "Construction", "Downtown"]
LEVEL_TO_GROUP = {"Sawmill": 0, "Cul-De-Sac": 1, "Construction": 2, "Downtown": 3}
GROUP_TO_LEVEL = {0: "Sawmill", 1: "Cul-De-Sac", 2: "Construction", 3: "Downtown"}

# Rank score thresholds (from [Manager+0xE0] entity data at +0x33/34/35)
# The cache stores raw score bytes (0-255). The game converts to rank via:
#   score >= 100 -> A rank
#   score >= 50  -> B rank
#   score >= 1   -> C rank
#   score == 0   -> not completed
THRESH_C = 1
THRESH_B = 50
THRESH_A = 100


def location_id_to_gid_rank(loc_id: int) -> typing.Optional[typing.Tuple[int, int]]:
    """Convert an AP location ID to (global_mission_id, required_rank).

    Location IDs are laid out as (Locations.py uses range(1,21), so 1-indexed):
      Sawmill C: 1-20, B: 21-40, A: 41-60
      Cul-De-Sac C: 61-80, B: 81-100, A: 101-120
      Construction C: 121-140, B: 141-160, A: 161-180
      Downtown C: 181-200, B: 201-220, A: 221-240

    Each block of 60 = one level (3 ranks × 20 missions).
    """
    if loc_id < 1 or loc_id > 240:
        return None  # not a mission location (could be interactable)

    adj = loc_id - 1  # convert to 0-indexed
    level_idx = adj // 60          # 0=Sawmill, 1=Cul-De-Sac, 2=Construction, 3=Downtown
    within_level = adj % 60
    rank_idx = within_level // 20  # 0=C, 1=B, 2=A
    slot = within_level % 20       # mission slot 0-19

    level_name = LEVEL_NAMES[level_idx]
    group = LEVEL_TO_GROUP[level_name]
    gid = group_slot_to_gid(group, slot)
    required_rank = rank_idx + 1   # 1=C, 2=B, 3=A

    return gid, required_rank


def gid_rank_to_location_id(gid: int, rank: int) -> int:
    """Convert (global_mission_id, rank) to AP location ID."""
    group, slot = gid_to_group_slot(gid)
    level_name = GROUP_TO_LEVEL[group]
    level_idx = LEVEL_NAMES.index(level_name)
    rank_idx = rank - 1  # C=0, B=1, A=2
    return level_idx * 60 + rank_idx * 20 + slot + 1  # +1 for 1-indexed IDs


def item_name_to_gid(item_name: str) -> typing.Optional[int]:
    """Convert an item name like 'Sawmill Mission 5 Unlock' to a GID.

    Mission 1 is always available (no unlock item exists for it).
    Mission N unlock → slot N-1 (0-indexed).
    """
    match = re.match(r"(Sawmill|Cul-De-Sac|Construction|Downtown) Mission (\d+) Unlock", item_name)
    if not match:
        return None
    level_name = match.group(1)
    mission_num = int(match.group(2))
    group = LEVEL_TO_GROUP[level_name]
    slot = mission_num - 1  # mission 1 = slot 0, mission 2 = slot 1, etc.
    return group_slot_to_gid(group, slot)


def _item_name_to_level_unlock(item_name: str) -> typing.Optional[str]:
    """Check if an item is a level unlock. Returns level name or None.

    Expected item names: 'Sawmill Unlock', 'Cul-De-Sac Unlock',
    'Construction Unlock', 'Downtown Unlock'.
    """
    match = re.match(r"(Sawmill|Cul-De-Sac|Construction|Downtown) Unlock$", item_name)
    if match:
        return match.group(1)
    return None


def _check_universal_tracker_version() -> bool:
    if tracker_loaded:
        match = re.search(r"v\d+.(\d+).(\d+)", UT_VERSION)
        if match and len(match.groups()) >= 2:
            if int(match.groups()[0]) >= 2 and int(match.groups()[1]) >= 12:
                return True
    return False


# ============================================================
# Interactable Location Detection
# ============================================================

# Build entity_name -> AP location ID lookup from Locations.py
# interactable_objects maps level -> [(entity_name, display_name), ...]
# In Locations.py, mission IDs use range(1,21) so occupy IDs 1-240,
# then index += 1 before interactables, so interactable IDs start at 241.
def _build_interactable_id_map() -> dict:
    """Build entity_name -> AP location ID from Locations.py interactable data."""
    result = {}
    # Mission locations consume IDs: 4 levels * 3 ranks * 20 missions = 240
    # In Locations.py: index starts at 0, each batch uses index+i for i in range(1,21),
    # then index += 20. After all missions, index = 240, then index += 1 = 241.
    loc_id = 241  # first interactable ID (240 mission slots + 1 offset)
    for level in ["Sawmill", "Cul-De-Sac", "Construction", "Downtown"]:
        for entity_name, display_name in interactable_objects[level]:
            result[entity_name] = loc_id
            loc_id += 1
    return result

INTERACTABLE_ID_MAP = _build_interactable_id_map()

# Local transform positions of each interactable entity, extracted from the FETM scene graph.
# These match the child entity's transform at runtime (entity+0x64 on depth=0 in the
# parent chain). Stable across sessions/seeds.
# Used to identify which interactable the King entered by matching runtime entity position.
INTERACTABLE_POSITIONS: dict[str, list] = {
    "1A_Int_Door01": [3339.7, 231.2, 1263.5],
    "1A_Int_Door02": [-2500.4, 3.6, 2003.7],
    "1A_Int_Door03": [2429.6, 1.1, -2655.1],
    "1A_Int_Door04": [3104.6, 6.1, 392.7],
    "1A_Int_Door05": [3450.7, 2.3, -219.9],
    "1A_Int_Door06": [3576.7, 2.6, -1996.8],
    "1A_Int_HP001": [910.2, -1.0, -1307.6],
    "1A_Int_HP002": [1069.9, -1.9, -549.9],
    "1A_Int_HP003": [1778.3, 0.0, -1985.0],
    "1A_Int_HP004": [1531.0, 0.0, -2091.5],
    "1A_Int_HP005": [1367.3, 0.0, -1878.1],
    "1A_Int_HP006": [3081.3, -5.0, -440.0],
    "1A_Int_HP007": [2802.7, -12.5, 286.7],
    "1A_Int_HP008": [3192.1, -7.2, -1814.3],
    "1A_Int_HP009": [-2461.0, 3.6, -1489.1],
    "1A_Int_HP010": [2583.9, 225.4, 2335.1],
    "1A_Int_HP011": [1888.4, 225.4, 2004.5],
    "1A_Int_HP012": [-3067.8, -0.2, -284.2],
    "1A_Int_HP013": [-3702.2, 0.3, -385.8],
    "1A_Int_HP014": [-1344.0, 91.3, -2202.6],
    "1A_Int_HP015": [-1584.9, 91.4, -2305.9],
    "1A_Int_HP016": [-1538.1, 91.3, -2584.0],
    "1A_Int_HP017": [-2899.4, 0.6, 447.4],
    "1A_Int_HP018": [-3396.2, 0.2, 1050.2],
    "1A_Int_HP019": [683.5, 0.4, -3611.6],
    "1A_Int_HP020": [3857.3, -9.7, -786.7],
    "1A_Int_HP021": [-2083.1, -4.3, 1533.2],
    "1A_Int_HP022": [-625.5, 0.6, 3893.0],
    "1A_Int_HP023": [-1055.1, 0.3, 3813.0],
    "1A_Int_HP024": [-909.0, 138.5, 1592.8],
    "1A_Int_HP025": [-2448.7, 225.3, -4104.8],
    "1A_Int_HP026": [-1606.5, -2.8, 1050.8],
    "1A_Int_HP027": [-1972.5, -9.5, 857.1],
    "1A_Int_HP028": [-2161.0, -9.8, 1375.7],
    "1A_Int_HP030": [-2780.1, 0.1, 1730.7],
    "1A_Int_HP031": [-2680.4, -0.5, 1769.4],
    "1A_Int_HP032": [3133.6, 225.3, 2760.8],
    "1A_Int_HP033": [3619.7, 225.6, 2091.6],
    "1A_Int_HP034": [1275.2, -0.2, 741.5],
    "1A_Int_HP035": [2416.1, 1.5, -2075.6],
    "1A_Int_HP036": [1795.6, 0.5, -3207.1],
    "1A_Int_HP037": [-1163.6, -9.1, -1593.5],
    "1A_Int_HP038": [-4543.9, 0.5, -2124.1],
    "1A_Int_HP039": [953.0, -1.1, -1731.4],
    "1A_Int_HP040": [1020.8, 227.5, 1474.5],
    "1A_Int_HP041": [1464.6, 226.3, 1651.1],
    "1A_Int_Ladder01": [-3051.0, -0.1, 1372.1],
    "1A_Int_Portaloo01": [2844.9, -1.1, 1010.5],
    "1A_Int_Shortcut01": [-485.2, 89.8, -1662.8],
    "1A_Int_Shortcut02": [357.0, 87.7, -2114.2],
    "1A_Int_Tree01": [-1230.4, 0.0, -515.9],
    "1A_Int_Tree02": [1985.4, 0.6, 169.9],
    "1PA_Int_BridgePanel01": [-8.3, 228.6, 3915.1],
    "2A_Bin 001": [-2015.2, 31.3, -1987.4],
    "2A_Bin 002": [-2131.6, 32.9, 416.3],
    "2A_Bin 003": [3966.3, 37.1, -1559.5],
    "2A_Bin 004": [4199.3, 38.5, -2515.5],
    "2A_Bin 005": [3448.2, 37.1, -3447.0],
    "2A_Bin 006": [83.5, 25.0, 1036.3],
    "2A_Bin 008": [1373.2, 25.2, 1741.2],
    "2A_Bin 009": [2107.8, 22.8, 742.1],
    "2A_Bin 010": [3113.4, 36.8, 1786.9],
    "2A_Bin 011": [-655.0, 25.0, -2785.5],
    "2A_Bin 013": [-2567.3, 25.0, -2838.1],
    "2A_Bin 015": [-991.6, 25.0, 704.1],
    "2A_Bin1": [-125.5, 29.5, -4003.4],
    "2A_Int_Door 001": [-1271.6, 100.0, -2834.6],
    "2A_Int_Door 002": [-1869.6, 86.2, -1117.9],
    "2A_Int_Door 003": [-1327.0, 100.0, 469.2],
    "2A_Int_Door 004": [228.4, 100.0, 1295.8],
    "2A_Int_Door 005": [2619.2, 81.8, -969.7],
    "2A_Int_Door 006": [2090.4, 81.8, -2858.5],
    "2A_Int_Door 007": [2427.6, 100.0, 487.9],
    "2A_Int_Door 008": [1734.2, 22.8, 3144.1],
    "2A_Int_Door 009": [-2428.6, 100.0, -3372.3],
    "2A_Int_Door 010": [-2985.3, 86.2, -1119.0],
    "2A_Int_Door 011": [-2394.6, 100.0, 1038.0],
    "2A_Int_Door 012": [271.5, 99.3, 2777.1],
    "2A_Int_Door 013": [3502.0, 100.0, 1039.8],
    "2A_Int_Door 014": [3295.4, 81.8, -3274.2],
    "2A_Int_Door 015": [3822.3, 81.8, -1384.4],
    "2A_Mailbox 001": [-2566.4, 26.4, 1101.1],
    "2A_Mailbox 002": [-15.3, 26.4, 2800.6],
    "2A_Mailbox1": [-852.5, 22.3, -663.3],
    "2A_Mailbox2": [-426.6, 29.6, -2350.0],
    "2A_Mailbox3": [-528.7, 26.4, -67.5],
    "2A_Mailbox4": [170.7, 24.9, 387.7],
    "2A_Mailbox5": [1558.7, 25.0, -69.1],
    "2A_Mailbox6": [1905.5, 22.8, -1276.2],
    "2A_Mailbox7": [1485.5, 30.9, -3169.2],
    "2A_conserv_glass 008": [429.1, 0.0, 1833.7],
    "2A_conservatory 001": [410.2, 0.0, 1831.2],
    "2A_crate 001": [573.5, 14.1, -1839.3],
    "2A_crate 002": [619.5, 14.1, -1709.8],
    "2A_treehouse 001": [3075.3, 23.2, 2816.2],
    "3A_Barrel01": [-3683.0, -1.3, -1864.8],
    "3A_Barrel02": [1810.3, -0.0, -3053.7],
    "3A_Barrel03": [-819.0, -0.0, 793.3],
    "3A_Barrel04": [-1632.5, 6.7, 998.7],
    "3A_Barrel05": [-1523.2, 0.0, -564.3],
    "3A_Barrel06": [-1793.0, -0.0, -545.8],
    "3A_Barrel07": [220.2, 4.6, 2647.3],
    "3A_Crate01": [-1500.1, 1.9, 2106.8],
    "3A_Crate02": [623.1, 341.6, 3114.7],
    "3A_Crate03": [1683.5, 5.4, 841.9],
    "3A_Crate04": [-268.9, 0.0, -3038.6],
    "3A_Crate05": [-1695.2, -3.0, 261.4],
    "3A_Crate06": [1591.1, 3.6, -757.4],
    "3A_Crate07": [2081.1, 347.8, 996.3],
    "3A_DiggerScoop": [30.7, -0.0, -1193.9],
    "3A_Door01": [502.7, 0.0, 2014.5],
    "3A_Door02": [-841.8, 0.0, 647.8],
    "3A_Door02_knocker": [-845.4, -0.0, 618.0],
    "3A_Door03": [-1713.6, -0.0, 473.1],
    "3A_Door03_knocker": [-1707.9, -0.4, 487.9],
    "3A_Door_Portaloo": [-3846.4, -0.0, -2959.4],
    "3A_LadderBase": [1089.2, 0.0, -2934.3],
    "3A_Manhole1": [-887.1, 0.0, 2554.0],
    "3A_Manhole2": [-123.4, 0.0, -2150.4],
    "3A_PipeEnd02": [-723.4, -0.0, -497.6],
    "3A_PipeEnd04": [-290.0, 0.0, 328.9],
    "3A_PipeEndRaised1": [-208.8, 7.2, 189.3],
    "3A_PipeFlat": [351.2, -0.0, 621.5],
    "3A_PipeRamp": [2263.9, 349.9, -434.5],
    "3A_PipeV": [-582.1, -2.9, 2096.4],
    "3A_Sandpile": [-3446.1, 6.3, 2312.4],
    "3A_Skip1": [-3661.1, -2.7, 370.4],
    "3A_Skip2": [-903.1, 0.0, -3410.3],
    "4A_HP 001": [1032.3, 10.0, 2518.7],
    "4A_HP 003": [2504.5, 10.0, 1309.0],
    "4A_HP 004": [1059.2, 10.0, 2710.0],
    "4A_HP 006": [-220.6, 9.1, -2332.5],
    "4A_HP 007": [2663.3, 10.0, -1206.3],
    "4A_HP 008": [-2459.6, -0.0, -1504.3],
    "4A_HP 009": [-971.8, 10.0, -226.6],
    "4A_HP 010": [2575.5, 10.0, -2051.4],
    "4A_HP 014": [-1979.2, 10.0, 2714.7],
    "4A_HP 015": [-125.3, 10.0, 1119.3],
    "4A_HP 017": [1460.8, 9.8, -2359.5],
    "4A_HP 019": [894.5, -0.0, -903.5],
    "4A_HP 022": [-1808.0, 10.0, 2026.3],
    "4A_HP 023": [-2562.8, 10.0, 1448.5],
    "4A_HP 025": [-2384.9, -0.0, -1904.8],
    "4A_HP 027": [-831.2, 10.0, -2355.3],
    "4A_HPskip 001": [-2378.7, 10.0, -26.4],
    "4A_Int_AptDoor_ 001": [81.3, 147.8, -2794.6],
    "4A_Int_AptDoor_ 03": [781.1, 147.2, 2723.3],
    "4A_Int_AptDoor_ 04": [3112.4, 147.2, 410.3],
    "4A_Int_AptDoor_01": [-2780.7, 147.8, -2540.7],
    "4A_Int_AptDoor_02": [-299.1, 147.2, 2723.3],
    "4A_Int_NewspaperMachine01": [-88.9, 10.0, -734.3],
    "4A_Int_SC03": [2201.5, -0.3, -880.0],
    "4A_Int_SC04": [-888.0, 0.0, 1437.2],
    "4A_Int_StoreDoor02": [-2522.7, 10.0, 729.6],
    "4A_SceneryProp_Car 006": [-759.1, 0.0, 2017.6],
    "4A_Subway1_entrance": [2887.9, 5.1, 1687.0],
    "4A_Subway1_exit": [2707.5, 5.1, 1687.0],
    "4A_Subway2_entrance": [-676.7, 9.2, -2456.1],
    "4A_Subway2_exit": [-676.7, 9.2, -2278.1],
    "4A_Telemaphone_door": [-550.0, 10.0, -1038.6],
    "4A_Telemaphone_door2": [-169.9, 10.0, -1038.6],
    "Prop Tree 001": [5707.3, 22.6, -2517.7],
    "Prop Tree 002": [4716.5, 22.6, 324.7],
    "Prop Tree 003": [4716.5, 22.6, 1477.5],
    "Prop Tree 004": [4716.5, 22.6, 2528.0],
    "Prop Tree 005": [5891.0, 22.6, -88.8],
    "Prop Tree 006": [7498.2, 22.6, -748.3],
    "Prop Tree 007": [3940.8, 22.6, 3623.4],
    "Prop Tree 008": [6185.3, 22.6, 3022.4],
    "Prop Tree 009": [3940.8, 22.6, -4946.5],
    "Prop Tree 010": [5207.8, 22.6, -4633.4],
    "Prop Tree 011": [-1714.4, 22.6, 4581.5],
    "Prop Tree 012": [-487.7, 22.6, 4006.7],
    "Prop Tree 013": [-4439.3, 22.6, -2517.7],
    "Prop Tree 014": [-4439.3, 22.6, -4077.5],
    "Prop Tree 015": [-5148.3, 22.6, -88.8],
    "Prop Tree 016": [-6120.7, 22.6, 2752.2],
    "Prop Tree 017": [-4223.9, 22.6, 3412.4],
    "Prop Tree 018": [-3446.6, 22.6, 6118.4],
    "Prop Tree 019": [-7218.2, 11.1, 1740.9],
    "Prop Tree 020": [-4439.3, 22.6, -7960.6],
    "Prop Tree 021": [2039.0, 22.6, -7960.6],
    "Prop Tree 022": [4010.7, 22.6, -7960.6],
    "Prop Tree 023": [-461.2, 22.6, -7960.6],
    "Prop Tree001": [5373.5, 22.6, -3548.8],
}

# Position tolerance for matching runtime entity positions to known positions.
# Sneak King world coordinates are large (thousands), so 5.0 units is very tight.
POSITION_MATCH_TOLERANCE = 5.0

def _positions_match(pos1: tuple, pos2: tuple) -> bool:
    """Check if two (x, y, z) positions are close enough to be the same interactable."""
    return (abs(pos1[0] - pos2[0]) < POSITION_MATCH_TOLERANCE and
            abs(pos1[1] - pos2[1]) < POSITION_MATCH_TOLERANCE and
            abs(pos1[2] - pos2[2]) < POSITION_MATCH_TOLERANCE)


# Entity name prefix -> AP level name
_ENTITY_PREFIX_TO_LEVEL = {
    "1A_": "Sawmill",
    "1PA_": "Sawmill",
    "2A_": "Cul-De-Sac",
    "Prop Tree": "Cul-De-Sac",
    "3A_": "Construction",
    "4A_": "Downtown",
}

def _entity_name_to_level(entity_name: str) -> typing.Optional[str]:
    """Determine which level an interactable entity belongs to from its name prefix."""
    for prefix, level in _ENTITY_PREFIX_TO_LEVEL.items():
        if entity_name.startswith(prefix):
            return level
    return None


# ============================================================
# Client
# ============================================================

class SneakKingCommandProcessor(ClientCommandProcessor):
    def __init__(self, ctx: cmmCtx):
        super().__init__(ctx)

    def _cmd_status(self):
        """Show current game connection and mission status."""
        ctx: SneakKingContext = self.ctx
        if not ctx.game_connected:
            logger.info("Not connected to game.")
            return
        mem = ctx.mem
        if not mem.ensure_ready():
            logger.info("Connected to xemu but cache not available.")
            return
        vis = sum(1 for g in range(80) if mem.read_ap_visible(g))
        done = sum(1 for g in range(80) if mem.read_rank(g) > 0)
        a_rank = sum(1 for g in range(80) if mem.read_rank(g) >= THRESH_A)
        logger.info(f"Visible: {vis}/80 | Completed: {done}/80 | A-rank: {a_rank}/80")
        logger.info(f"Locations checked: {len(ctx.checked_locations)}")

    def _cmd_resync(self):
        """Force re-sync of all received items to game memory."""
        ctx: SneakKingContext = self.ctx
        ctx._items_synced_index = 0
        logger.info("Will re-sync all items on next cycle.")


class SneakKingContext(cmmCtx):
    command_processor = SneakKingCommandProcessor
    game = "Sneak King"
    tags = {"AP"}
    game_connected: bool = False
    slot_data: dict | None = {}
    checked_locations: set = set()

    def __init__(self, server_address, password):
        super().__init__(server_address, password)
        self.items_handling = 0b111
        self.mem = SneakKingMemory()
        self._items_synced_index = 0  # tracks how many received items we've processed
        self._last_ranks: dict[int, int] = {}  # gid -> rank, for change detection
        # Interactable detection state
        self._last_interaction_va: int = 0  # last entity pointer seen at King+0x32C
        self._interactable_positions: dict[str, tuple] = {}  # entity_name -> (x, y, z) runtime positions
        self._position_to_entity: dict = {}  # will be built from slot_data or discovered at runtime

    async def server_auth(self, password_requested: bool = False):
        if password_requested and not self.password:
            await super(SneakKingContext, self).server_auth(password_requested)
        await self.get_username()
        await self.send_connect()

    def on_package(self, cmd: str, args: dict):
        super().on_package(cmd, args)
        if cmd in {"Connected"}:
            self.slot = args["slot"]
            self.slot_data = args["slot_data"]
            self.team = args["team"]
            if "death_link" in args["slot_data"]:
                Utils.async_start(self.update_death_link(bool(args["slot_data"]["death_link"])))
        elif cmd == "RoomInfo":
            self.seed_name = args["seed_name"]

    def on_deathlink(self, data: typing.Dict[str, typing.Any]) -> None:
        super().on_deathlink(data)
        # TODO: Send death to game (freeze king? force mission fail?)

    async def disconnect(self, allow_autoreconnect: bool = False):
        await super().disconnect()
        self.slot = None
        self.slot_data = None
        self.team = None
        self.checked_locations = set()
        self.seed_name = None
        self._items_synced_index = 0
        self._last_ranks.clear()
        self._last_interaction_va = 0

    def make_gui(self) -> "type[kvui.GameManager]":
        from kvui import GameManager
        class SneakKingManager(GameManager):
            logging_pairs = [("Client", "Archipelago")]
            base_title = "Archipelago Sneak King Client"
        if not _check_universal_tracker_version():
            return SneakKingManager
        class TrackerManager(super().make_gui()):
            logging_pairs = [("Client", "Archipelago")]
            base_title = f"Archipelago Sneak King Client with {UT_VERSION}"
        return TrackerManager

    # ----------------------------------------------------------
    # Game Integration
    # ----------------------------------------------------------

    def _has_level_access(self, level_name: str) -> bool:
        """Check if the player currently has access to a level."""
        if not self.slot_data:
            return False

        starting_level = self.slot_data.get("starting_level", 0)
        starting_name = LEVEL_NAMES[starting_level]

        unlock_method = self.slot_data.get("level_unlock_method", 1)

        if unlock_method == 1:
            # unlock_item: starting level is free, others need the unlock item
            if level_name == starting_name:
                return True
            level_unlock = f"{level_name} Unlock"
            for item in self.items_received:
                received_name = self.item_names.lookup_in_game(item.item)
                if received_name == level_unlock:
                    return True
            return False
        else:
            # x_missions: levels unlock in a chain based on completing X missions
            # in the previous level. level_order from slot_data defines the chain,
            # but must always start from starting_level.
            level_order = self.slot_data.get("level_order", LEVEL_NAMES)
            unlock_range = self.slot_data.get("level_unlock_range", 20)

            # Rebuild the chain so it starts from starting_level
            if starting_name in level_order:
                start_idx = level_order.index(starting_name)
                # Rotate so starting_level is first
                level_order = level_order[start_idx:] + level_order[:start_idx]

            if level_name not in level_order:
                return False

            level_idx = level_order.index(level_name)
            if level_idx == 0:
                return True  # starting level is always accessible

            # Need unlock_range completions in previous level
            prev_level = level_order[level_idx - 1]
            prev_group = LEVEL_TO_GROUP[prev_level]
            completions = sum(
                1 for s in range(20)
                if self.mem.read_rank(group_slot_to_gid(prev_group, s)) >= THRESH_C
            )
            return completions >= unlock_range

    async def receive_items(self):
        """Process newly received items and write AP visibility bits to game memory."""
        if not self.mem.ensure_ready():
            return

        items = self.items_received
        changed = False

        # Process new items since last sync
        if self._items_synced_index < len(items):
            for i in range(self._items_synced_index, len(items)):
                item = items[i]
                item_name = self.item_names.lookup_in_game(item.item)

                # Level unlock item -> set availability bit in cache+0xA4
                level_unlock = _item_name_to_level_unlock(item_name)
                if level_unlock is not None:
                    group = LEVEL_TO_GROUP[level_unlock]
                    self.mem.set_level_available(group)
                    changed = True
                    logger.info(f"Level unlocked: {level_unlock} (group {group})")

                # Mission unlock item -> set AP visibility bit
                gid = item_name_to_gid(item_name)
                if gid is not None:
                    if not self.mem.read_ap_visible(gid):
                        self.mem.write_ap_visible(gid, True)
                        changed = True
                        logger.debug(f"Unlocked mission GID {gid}: {item_name}")

                # TODO: Handle other item types (Progressive Flourish, Progressive Chain,
                #       traps, etc.)

            self._items_synced_index = len(items)

        if changed:
            self.mem.set_dirty()

    async def check_locations(self):
        """Read mission scores from game memory and report completed locations."""
        if not self.mem.ensure_ready():
            return

        new_locations = set()
        enabled_ranks = self.slot_data.get("enabled_ranks", ["C", "B", "A"]) if self.slot_data else ["C", "B", "A"]
        thresh_map = {"C": THRESH_C, "B": THRESH_B, "A": THRESH_A}
        # gid_rank_to_location_id expects rank 1=C, 2=B, 3=A (location index, not score)
        rank_index_map = {"C": 1, "B": 2, "A": 3}

        for gid in range(80):
            score = self.mem.read_rank(gid)

            # Check each enabled rank threshold
            for rank_name in enabled_ranks:
                threshold = thresh_map[rank_name]
                if score >= threshold:
                    loc_id = gid_rank_to_location_id(gid, rank_index_map[rank_name])
                    if loc_id not in self.checked_locations:
                        new_locations.add(loc_id)

            # Track score changes for logging
            prev = self._last_ranks.get(gid, 0)
            if score != prev:
                if score > 0:
                    group, slot = gid_to_group_slot(gid)
                    level = GROUP_TO_LEVEL[group]
                    if score >= THRESH_A:
                        rank_str = "A"
                    elif score >= THRESH_B:
                        rank_str = "B"
                    elif score >= THRESH_C:
                        rank_str = "C"
                    else:
                        rank_str = "?"
                    logger.info(f"Mission completed: {level} Mission {slot + 1} — Rank {rank_str} (score {score})")
                self._last_ranks[gid] = score

        if new_locations:
            self.checked_locations |= new_locations
            await self.send_msgs([{"cmd": "LocationChecks", "locations": list(new_locations)}])

    async def check_interactables(self):
        """Detect interactable usage by reading King+0x32C entity pointer.

        When the King enters a hiding spot, climbs a ladder, opens a door, etc.,
        [King+0x32C] is set to the entity pointer. When idle, it's 0.

        We detect new interactions, read the entity's local transform position,
        and match against INTERACTABLE_POSITIONS to identify the AP location.
        """
        if not self.mem.ensure_ready():
            return

        result = self.mem.read_interaction_entity()

        if result is None:
            if self._last_interaction_va != 0:
                self._last_interaction_va = 0
            return

        entity_va, x, y, z = result

        # Only trigger on NEW interactions
        if entity_va == self._last_interaction_va:
            return
        self._last_interaction_va = entity_va

        pos = (round(x, 1), round(y, 1), round(z, 1))

        # Match position against known interactable positions
        matched_entity = None
        best_dist = float('inf')
        best_name = None
        for ent_name, known_pos in INTERACTABLE_POSITIONS.items():
            dist = max(abs(pos[0] - known_pos[0]),
                       abs(pos[1] - known_pos[1]),
                       abs(pos[2] - known_pos[2]))
            if dist < best_dist:
                best_dist = dist
                best_name = ent_name
            if _positions_match(pos, tuple(known_pos)):
                matched_entity = ent_name
                break

        if matched_entity is None:
            logger.info(f"[Interactable] NO MATCH at {pos} (closest: {best_name} dist={best_dist:.1f})")
            return

        # Check level access
        entity_level = _entity_name_to_level(matched_entity)
        if entity_level and not self._has_level_access(entity_level):
            logger.info(f"[Interactable] Matched {matched_entity} but {entity_level} not unlocked")
            return

        # Look up the AP location ID
        loc_id = INTERACTABLE_ID_MAP.get(matched_entity)
        if loc_id is None:
            logger.info(f"[Interactable] {matched_entity} has no AP location ID")
            return

        if loc_id not in self.checked_locations:
            self.checked_locations.add(loc_id)
            display_name = matched_entity
            for loc in all_locations:
                if loc.id == loc_id:
                    display_name = loc.name
                    break
            logger.info(f"Interactable checked: {display_name} (loc_id={loc_id})")
            await self.send_msgs([{"cmd": "LocationChecks", "locations": [loc_id]}])

    async def check_goal(self):
        """Check if the goal condition is met."""
        if not self.slot_data or not self.mem.ensure_ready():
            return

        goal_type = self.slot_data.get("goal", 0)
        goal_range = self.slot_data.get("goal_range", 20)

        if goal_type == 0:
            # complete_x_missions: count missions with score >= C threshold
            completed = sum(1 for gid in range(80) if self.mem.read_rank(gid) >= THRESH_C)
            if completed >= goal_range:
                await self.send_msgs([{"cmd": "StatusUpdate", "status": ClientStatus.CLIENT_GOAL}])

        elif goal_type == 1:
            # complete_x_a_ranks: count missions with score >= A threshold
            a_count = sum(1 for gid in range(80) if self.mem.read_rank(gid) >= THRESH_A)
            if a_count >= goal_range:
                await self.send_msgs([{"cmd": "StatusUpdate", "status": ClientStatus.CLIENT_GOAL}])

    def update_level_availability(self):
        """Check all levels and set availability bits for accessible ones.

        Called every tick so x_missions unlocks happen immediately
        when the completion threshold is met, not just on item receipt.
        Also ensures mission 1 is visible for each accessible level.
        """
        if not self.slot_data or not self.mem.ensure_ready():
            return

        for level_name in LEVEL_NAMES:
            if self._has_level_access(level_name):
                group = LEVEL_TO_GROUP[level_name]
                self.mem.set_level_available(group)
                # Ensure mission 1 scroll is visible
                gid = group_slot_to_gid(group, 0)
                if not self.mem.read_ap_visible(gid):
                    self.mem.write_ap_visible(gid, True)
                    self.mem.set_dirty()
                    logger.info(f"Mission 1 visible for {level_name}")


# ============================================================
# Sync Task
# ============================================================

async def sneak_king_sync_task(ctx: SneakKingContext):
    logger.info("Starting Sneak King connector...")
    while not ctx.exit_event.is_set():
        if ctx.game_connected:
            if ctx.slot:
                try:
                    # Validate game connection is still alive
                    if not ctx.mem.ensure_ready():
                        logger.info("Lost connection to game. Reconnecting...")
                        ctx.game_connected = False
                        await asyncio.sleep(3)
                        continue

                    await ctx.receive_items()
                    await ctx.check_locations()
                    await ctx.check_interactables()
                    ctx.update_level_availability()
                    await ctx.check_goal()
                    await asyncio.sleep(0.5)
                except Exception:
                    import traceback
                    logger.info(traceback.format_exc())
                    ctx.game_connected = False
                    await asyncio.sleep(3)
            else:
                await asyncio.sleep(1)
        else:
            # Attempt connection to xemu
            try:
                if ctx.mem.connect():
                    logger.info("Connected to Sneak King!")
                    ctx.game_connected = True
                    ctx._items_synced_index = 0  # re-sync items on reconnect
                    ctx._last_ranks.clear()
                    ctx._last_interaction_va = 0
                else:
                    await asyncio.sleep(3)
            except Exception:
                await asyncio.sleep(3)


# ============================================================
# Launch
# ============================================================

async def _run_game(rom: str):
    import os
    auto_start = settings.get_settings().sneak_king_options.rom_start

    if auto_start is True:
        xemu_path = settings.get_settings().sneak_king_options.xemu_path
        subprocess.Popen(
            [
                xemu_path,
                "-dvd_path",
                os.path.realpath(rom),
            ],
            cwd=Utils.local_path("."),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


async def _patch_and_run_game(patch_file: str):
    metadata, output_file = Patch.create_rom_file(patch_file)
    Utils.async_start(_run_game(output_file))
    return metadata


def launch(*args):
    async def main(args):
        if args.patch_file:
            await asyncio.create_task(_patch_and_run_game(args.patch_file))
        ctx = SneakKingContext(args.connect, args.password)
        ctx.server_task = asyncio.create_task(server_loop(ctx), name="ServerLoop")
        if gui_enabled:
            if tracker_loaded:
                ctx.run_generator()
            ctx.run_gui()
        ctx.run_cli()
        ctx.sync_task = asyncio.create_task(sneak_king_sync_task(ctx), name="Sneak King Sync Task")

        await ctx.exit_event.wait()
        ctx.server_address = None

        await ctx.shutdown()

    parser = get_base_parser()
    parser.add_argument("patch_file", default="", type=str, nargs="?", help="Path to an APSK file")
    args = parser.parse_args(args)

    import colorama

    colorama.just_fix_windows_console()
    asyncio.run(main(args))
    colorama.deinit()
