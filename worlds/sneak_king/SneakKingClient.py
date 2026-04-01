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

LEVEL_NAMES = ["Sawmill", "Cul-De-Sac", "Construction", "Downtown"]
LEVEL_TO_GROUP = {"Sawmill": 0, "Cul-De-Sac": 1, "Construction": 2, "Downtown": 3}
GROUP_TO_LEVEL = {0: "Sawmill", 1: "Cul-De-Sac", 2: "Construction", 3: "Downtown"}

THRESH_C = 1
THRESH_B = 50
THRESH_A = 100



def gid_rank_to_location_id(gid: int, rank: int) -> int:
    """Convert (global_mission_id, rank) to a location ID."""
    group, slot = gid_to_group_slot(gid)
    level_idx = LEVEL_NAMES.index(GROUP_TO_LEVEL[group])
    return level_idx * 60 + (rank - 1) * 20 + slot + 1


def item_name_to_gid(item_name: str) -> typing.Optional[int]:
    """Convert a mission unlock item name to a GID, or None if not a mission unlock."""
    match = re.match(r"(Sawmill|Cul-De-Sac|Construction|Downtown) Mission (\d+) Unlock", item_name)
    if not match:
        return None
    group = LEVEL_TO_GROUP[match.group(1)]
    slot = int(match.group(2)) - 1
    return group_slot_to_gid(group, slot)


def _item_name_to_level_unlock(item_name: str) -> typing.Optional[str]:
    """Return the level name if item_name is a level unlock item, otherwise None."""
    match = re.match(r"(Sawmill|Cul-De-Sac|Construction|Downtown) Unlock$", item_name)
    return match.group(1) if match else None


def _check_universal_tracker_version() -> bool:
    if tracker_loaded:
        match = re.search(r"v\d+.(\d+).(\d+)", UT_VERSION)
        if match and len(match.groups()) >= 2:
            if int(match.groups()[0]) >= 2 and int(match.groups()[1]) >= 12:
                return True
    return False


def _build_interactable_id_map() -> dict:
    result = {}
    loc_id = 241
    for level in ["Sawmill", "Cul-De-Sac", "Construction", "Downtown"]:
        for entity_name, display_name in interactable_objects[level]:
            result[entity_name] = loc_id
            loc_id += 1
    return result

INTERACTABLE_ID_MAP = _build_interactable_id_map()

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
    "2A_Int_Door 013": [3502.0, 100.0, 1039.8],
    "2A_Int_Door 014": [3295.4, 81.8, -3274.2],
    "2A_Int_Door 015": [3822.3, 81.8, -1384.4],
    "2A_Mailbox2": [-426.6, 29.6, -2350.0],
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
    "3A_Door02_knocker": [-845.4, -0.0, 618.0],
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
}

POSITION_MATCH_TOLERANCE = 5.0

def _positions_match(pos1: tuple, pos2: tuple) -> bool:
    return (abs(pos1[0] - pos2[0]) < POSITION_MATCH_TOLERANCE and
            abs(pos1[1] - pos2[1]) < POSITION_MATCH_TOLERANCE and
            abs(pos1[2] - pos2[2]) < POSITION_MATCH_TOLERANCE)


_ENTITY_PREFIX_TO_LEVEL = {
    "1A_": "Sawmill",
    "1PA_": "Sawmill",
    "2A_": "Cul-De-Sac",
    "Prop Tree": "Cul-De-Sac",
    "3A_": "Construction",
    "4A_": "Downtown",
}

def _entity_name_to_level(entity_name: str) -> typing.Optional[str]:
    for prefix, level in _ENTITY_PREFIX_TO_LEVEL.items():
        if entity_name.startswith(prefix):
            return level
    return None


class SneakKingCommandProcessor(ClientCommandProcessor):
    def __init__(self, ctx: cmmCtx):
        super().__init__(ctx)


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
        self._items_synced_index = 0
        self._last_ranks: dict[int, int] = {}
        self._last_interaction_va: int = 0
        self._interactable_positions: dict[str, tuple] = {}
        self._position_to_entity: dict = {}
        self._unlocked_levels: set[str] = set()

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
        self._unlocked_levels.clear()

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

    def _has_level_access(self, level_name: str) -> bool:
        """Check if the player currently has access to a level.

        Starting level is always accessible. Level unlock items are always
        checked regardless of settings. x_missions chain is additionally
        checked when level_unlock_method is set to that mode.
        """
        if not self.slot_data:
            return False

        starting_level = self.slot_data.get("starting_level", 0)
        starting_name = LEVEL_NAMES[starting_level]

        if level_name == starting_name:
            return True

        level_unlock = f"{level_name} Unlock"
        for item in self.items_received:
            if self.item_names.lookup_in_game(item.item) == level_unlock:
                return True

        unlock_method = self.slot_data.get("level_unlock_method", 1)
        if unlock_method != 1:
            level_order = self.slot_data.get("level_order", LEVEL_NAMES)
            unlock_range = self.slot_data.get("level_unlock_range", 20)

            if level_name in level_order:
                level_idx = level_order.index(level_name)
                prev_level = level_order[level_idx - 1]
                prev_group = LEVEL_TO_GROUP[prev_level]
                completions = sum(
                    1 for s in range(20)
                    if self.mem.read_rank(group_slot_to_gid(prev_group, s)) >= THRESH_C
                )
                if completions >= unlock_range:
                    return True

        return False

    async def receive_items(self):
        if not self.mem.ensure_ready():
            return

        items = self.items_received
        changed = False

        if self._items_synced_index < len(items):
            for i in range(self._items_synced_index, len(items)):
                item = items[i]
                item_name = self.item_names.lookup_in_game(item.item)

                level_unlock = _item_name_to_level_unlock(item_name)
                if level_unlock is not None:
                    group = LEVEL_TO_GROUP[level_unlock]
                    mission1_gid = group_slot_to_gid(group, 0)
                    if not self.mem.read_visible(mission1_gid):
                        self.mem.write_visible(mission1_gid, True)
                    changed = True
                    logger.info(f"Level unlocked: {level_unlock} (group {group})")

                gid = item_name_to_gid(item_name)
                if gid is not None:
                    group, _ = gid_to_group_slot(gid)
                    level_name = GROUP_TO_LEVEL[group]
                    if self._has_level_access(level_name) and not self.mem.read_visible(gid):
                        self.mem.write_visible(gid, True)
                        changed = True
                        logger.debug(f"Unlocked mission GID {gid}: {item_name}")

            self._items_synced_index = len(items)

        if changed:
            self.mem.set_dirty()

    async def check_locations(self):
        if not self.mem.ensure_ready():
            return

        new_locations = set()
        enabled_ranks = self.slot_data.get("enabled_ranks", ["C", "B", "A"]) if self.slot_data else ["C", "B", "A"]
        thresh_map = {"C": THRESH_C, "B": THRESH_B, "A": THRESH_A}
        rank_index_map = {"C": 1, "B": 2, "A": 3}

        for gid in range(80):
            group, slot = gid_to_group_slot(gid)
            level_name = GROUP_TO_LEVEL[group]
            if not self._has_level_access(level_name):
                continue

            score = self.mem.read_rank(gid)

            for rank_name in enabled_ranks:
                if score >= thresh_map[rank_name]:
                    loc_id = gid_rank_to_location_id(gid, rank_index_map[rank_name])
                    if loc_id not in self.checked_locations:
                        new_locations.add(loc_id)

            prev = self._last_ranks.get(gid, 0)
            if score != prev:
                if score > 0:
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
        if not self.mem.ensure_ready():
            return

        result = self.mem.read_interaction_entity()

        if result is None:
            if self._last_interaction_va != 0:
                self._last_interaction_va = 0
            return

        entity_va, positions = result

        if entity_va == self._last_interaction_va:
            return
        self._last_interaction_va = entity_va

        matched_entity = None
        best_dist = float('inf')
        best_name = None
        for _va, x, y, z in positions:
            pos = (round(x, 1), round(y, 1), round(z, 1))
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
            if matched_entity:
                break

        if matched_entity is None:
            logger.info(f"[Interactable] NO MATCH (closest: {best_name} dist={best_dist:.1f})")
            return

        entity_level = _entity_name_to_level(matched_entity)
        if entity_level and not self._has_level_access(entity_level):
            logger.info(f"[Interactable] Matched {matched_entity} but {entity_level} not unlocked")
            return

        loc_id = INTERACTABLE_ID_MAP.get(matched_entity)
        if loc_id is None:
            logger.info(f"[Interactable] {matched_entity} has no location ID")
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
        if not self.slot_data or not self.mem.ensure_ready():
            return

        goal_type = self.slot_data.get("goal", 0)
        goal_range = self.slot_data.get("goal_range", 20)

        if goal_type == 0:
            completed = sum(1 for gid in range(80) if self.mem.read_rank(gid) >= THRESH_C)
            if completed >= goal_range:
                await self.send_msgs([{"cmd": "StatusUpdate", "status": ClientStatus.CLIENT_GOAL}])

        elif goal_type == 1:
            a_count = sum(1 for gid in range(80) if self.mem.read_rank(gid) >= THRESH_A)
            if a_count >= goal_range:
                await self.send_msgs([{"cmd": "StatusUpdate", "status": ClientStatus.CLIENT_GOAL}])

    def update_level_availability(self):
        if not self.slot_data or not self.mem.ensure_ready():
            return

        for level_name in LEVEL_NAMES:
            if not self._has_level_access(level_name):
                continue

            group = LEVEL_TO_GROUP[level_name]
            changed = False

            if level_name not in self._unlocked_levels:
                self._unlocked_levels.add(level_name)

                gid = group_slot_to_gid(group, 0)
                if not self.mem.read_visible(gid):
                    self.mem.write_visible(gid, True)
                    changed = True

                for item in self.items_received:
                    item_name = self.item_names.lookup_in_game(item.item)
                    gid = item_name_to_gid(item_name)
                    if gid is not None:
                        item_group, _ = gid_to_group_slot(gid)
                        if item_group == group and not self.mem.read_visible(gid):
                            self.mem.write_visible(gid, True)
                            changed = True

                logger.info(f"Level unlocked: {level_name}")

            if changed:
                self.mem.set_dirty()


async def sneak_king_sync_task(ctx: SneakKingContext):
    logger.info("Starting Sneak King connector...")
    while not ctx.exit_event.is_set():
        if ctx.game_connected:
            if ctx.slot:
                try:
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
            try:
                if ctx.mem.connect():
                    logger.info("Connected to Sneak King!")
                    ctx.game_connected = True
                    ctx._items_synced_index = 0
                    ctx._last_ranks.clear()
                    ctx._last_interaction_va = 0
                else:
                    await asyncio.sleep(3)
            except Exception:
                await asyncio.sleep(3)


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
