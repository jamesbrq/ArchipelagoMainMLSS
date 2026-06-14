import asyncio
import struct
import subprocess
import traceback
import typing
import settings
import Patch
import Utils
from CommonClient import ClientCommandProcessor, get_base_parser, gui_enabled, logger, server_loop
import dolphin_memory_engine as dolphin
from NetUtils import NetworkItem, ClientStatus
from . import Ghosts
from .Data import location_gsw_info, location_to_unit
from .Items import items_by_id

from .ttyd_runtime import (
    _on_ghost_disconnect,
    _on_inbound_hit,
    _vlink_on_bounce,
    vlink_force_presence,
    vlink_clear_loopback,
    ttyd_ghost_sync_task,
)


RECEIVED_INDEX = 0x803DB860
RECEIVED_ITEM_ARRAY = 0x80001000
RECEIVED_LENGTH = 0x80000FFC
SEED = 0x80003210
GP_BASE = 0x803DAC18
GSWF_BASE = 0x178
GSW0 = 0x174
GSW_BASE = 0x578
ROOM = 0x803DF728
GAME_ID_ADDRESS = 0x80000000
EXPECTED_GAME_ID = b"G8ME01"

def _check_universal_tracker_version() -> bool:
    import re
    if tracker_loaded:
        match = re.search(r"v\d+.(\d+).(\d+)", UT_VERSION)
        if len(match.groups()) < 2:
            return False
        if int(match.groups()[0]) < 2:
            return False
        if int(match.groups()[1]) < 12:
            return False
        return True
    return False
tracker_loaded = False
try:
    from worlds.tracker.TrackerClient import TrackerGameContext as cmmCtx, UT_VERSION
    tracker_loaded = True
except ModuleNotFoundError:
    from CommonClient import CommonContext as cmmCtx
    tracker_loaded = False
def validate_connection() -> bool:
    """Verify DME is hooked to TTYD by checking the GameCube disc Game ID in memory."""
    try:
        game_id = dolphin.read_bytes(GAME_ID_ADDRESS, 6)
        return game_id == EXPECTED_GAME_ID
    except Exception:
        return False
def read_string(address: int, length: int):
    try:
        return dolphin.read_bytes(address, length).decode().strip("\0")
    except Exception as e:
        logger.error(f"Error reading string from address {hex(address)}: {e}")
        return ""
def get_rom_item_id(item: NetworkItem):
    return items_by_id[item.item].rom_id
def _get_bit_address(bit_number: int) -> tuple:
    word_index = bit_number >> 5
    bit_position = bit_number & 0x1F
    word_address = GP_BASE + (word_index * 4) + GSWF_BASE
    byte_within_word = 3 - (bit_position >> 3)
    byte_address = word_address + byte_within_word
    bit = bit_position & 0x7
    return byte_address, bit
def gswf_set(bit_number: int):
    result = _get_bit_address(bit_number)
    if not result: return False
    byte_address, bit = result
    current_byte = dolphin.read_byte(byte_address)
    bit_mask = 1 << bit
    new_byte = current_byte | bit_mask
    dolphin.write_byte(byte_address, new_byte)
    return result
def gswf_check(bit_number: int) -> bool:
    result = _get_bit_address(bit_number)
    if not result: return False
    byte_address, bit = result
    current_byte = dolphin.read_byte(byte_address)
    bit_mask = 1 << bit
    return bool(current_byte & bit_mask)
def gswf_clear(bit_number: int):
    """Clear a single GSWF bit (set to 0). Sibling to gswf_set."""
    result = _get_bit_address(bit_number)
    if not result: return False
    byte_address, bit = result
    current_byte = dolphin.read_byte(byte_address)
    bit_mask = 1 << bit
    new_byte = current_byte & ~bit_mask & 0xFF
    dolphin.write_byte(byte_address, new_byte)
    return result
def gsw_set(index, value):
    dolphin.write_word(GP_BASE + GSW0, value) if index == 0 else dolphin.write_byte(GP_BASE + index + GSW_BASE, value)
def gsw_check(index):
    return dolphin.read_word(GP_BASE + GSW0) if index == 0 else dolphin.read_byte(GP_BASE + index + GSW_BASE)




class TTYDCommandProcessor(ClientCommandProcessor):
    def __init__(self, ctx):
        super().__init__(ctx)


    def _cmd_ghost(self, *args):
        """Manage ghost peer settings.

        Subcommands:
          /ghost test [N]                  - toggle single-client loopback (N ghosts, 1..32)
          /ghost hammertest [on|off] [sec] - solo: auto-hammer yourself on a timer
          /ghost names [on|off|toggle]     - hide/show your name tag
          /ghost friendly_fire [on|off]    - toggle FF for your hammer
          /ghost team join <color>         - join red/blue/green/yellow
          /ghost team leave                - clear team membership
          /ghost team status               - show your team / FF state
          /ghost team list                 - list all peers grouped by team
        """
        if not args:
            logger.info("ghost: subcommands - test / hammertest / names / friendly_fire / team")
            return
        sub = args[0].strip().lower()
        rest = args[1:]
        if sub == "test":
            self._ghost_test(*rest)
        elif sub in ("hammertest", "ht"):
            self._ghost_hammertest(*rest)
        elif sub == "names":
            self._ghost_names(*rest)
        elif sub in ("friendly_fire", "ff"):
            self._ghost_friendly_fire(*rest)
        elif sub == "team":
            self._ghost_team(*rest)
        else:
            logger.info(f"ghost: unknown subcommand '{sub}'. "
                        f"Use test/hammertest/names/friendly_fire/team.")



    def _cmd_gswf(self, *args):
        """Manipulate GSWF (global state word flag) bits. Debug only.

        Subcommands:
          /gswf set <bit_number>
          /gswf check <bit_number>
        """
        if not args:
            logger.info("gswf: subcommands - set / check")
            return
        sub = args[0].strip().lower()
        rest = args[1:]
        if sub == "set":
            if not rest:
                logger.info("gswf: usage: /gswf set <bit_number>")
                return
            self._gswf_set(rest[0])
        elif sub == "check":
            if not rest:
                logger.info("gswf: usage: /gswf check <bit_number>")
                return
            self._gswf_check(rest[0])
        else:
            logger.info(f"gswf: unknown subcommand '{sub}'. Use set/check.")

    def _cmd_gsw(self, *args):
        """Manipulate GSW (global state word) values. Debug only.

        Subcommands:
          /gsw set <index> <value>
          /gsw check <index>
        """
        if not args:
            logger.info("gsw: subcommands - set / check")
            return
        sub = args[0].strip().lower()
        rest = args[1:]
        if sub == "set":
            if len(rest) < 2:
                logger.info("gsw: usage: /gsw set <index> <value>")
                return
            self._gsw_set(rest[0], rest[1])
        elif sub == "check":
            if not rest:
                logger.info("gsw: usage: /gsw check <index>")
                return
            self._gsw_check(rest[0])
        else:
            logger.info(f"gsw: unknown subcommand '{sub}'. Use set/check.")


    def _gswf_set(self, bit_number: int):
        """Used to manually set a GSWF bit."""
        byte_address, bit = gswf_set(int(bit_number))
        logger.info(f"Bit {bit} written at {byte_address}")

    def _gswf_check(self, bit_number: int):
        """Used to manually check a GSWF bit."""
        result = gswf_check(int(bit_number))
        logger.info(f"GSWF Check: 0x{format(result, 'x')}")

    def _gsw_set(self, gsw: int, value: int):
        """Used to manually set a GSW flag."""
        gsw_set(int(gsw), int(value))

    def _gsw_check(self, gsw: int):
        """Used to manually check a GSW flag."""
        result = gsw_check(int(gsw))
        logger.info(f"GSWF Check: {result}")

    def _ghost_test(self, *args):
        """Toggle the single-player ghost loopback test.

        /ghost test         - toggle on/off (keeps the last ghost count)
        /ghost test <N>     - turn on with N synthetic ghosts (1..32) trailing you
        """
        ctx = self.ctx
        if args:
            try:
                count = max(1, min(int(args[0]), Ghosts.MAX_PEERS))
            except ValueError:
                logger.info(f"ghost test: count must be a number (1..{Ghosts.MAX_PEERS}).")
                return
            ctx._ghost_loopback_count = count
            ctx._ghost_loopback_active = True
            logger.info(f"Ghost loopback test ON with {count} ghost(s) trailing you to your "
                        f"right. Note: only the first maxRenderedPeers (default 12) actually "
                        f"render \u2014 raise that GhostState tunable to see all {count}.")
            return

        ctx._ghost_loopback_active = not getattr(ctx, "_ghost_loopback_active", False)
        if ctx._ghost_loopback_active:
            cnt = int(getattr(ctx, "_ghost_loopback_count", 1) or 1)
            logger.info(f"Ghost loopback test ON ({cnt} ghost(s)). A translucent ghost should "
                        f"appear a short distance to your right, mirroring your actions in real "
                        f"time.")
        else:
            vlink_clear_loopback(ctx)
            logger.info("Ghost loopback test OFF.")

    def _ghost_hammertest(self, *args):
        """Toggle the solo auto-hammer test. While on, the client simulates
        an inbound hammer hit on you every N seconds (default 10) by writing
        the mod's PENDING_HIT slot, exactly as a real peer's Bounce would.
        Lets you verify the victim-side stagger reaction - including the
        defer-while-mid-swing fix - without a second client. Independent of
        /ghost test, though running both gives you a visible ghost too.

        Usage:
          /ghost hammertest               - toggle on/off
          /ghost hammertest on|off        - set explicitly
          /ghost hammertest [on] <sec>    - set the interval in seconds
        """
        ctx = self.ctx
        mode = "toggle"
        interval = None
        for a in args:
            al = a.strip().lower()
            if al in ("on", "true"):
                mode = "on"
            elif al in ("off", "false"):
                mode = "off"
            elif al == "toggle":
                mode = "toggle"
            else:
                try:
                    interval = float(a)
                except ValueError:
                    pass

        if mode == "on":
            new_state = True
        elif mode == "off":
            new_state = False
        else:
            new_state = not getattr(ctx, "_ghost_autohammer_active", False)

        if interval is not None and interval > 0:
            ctx._ghost_autohammer_interval = interval

        ctx._ghost_autohammer_active = new_state
        ctx._ghost_autohammer_last_t = None  # re-arm; first hit after one interval

        if new_state:
            iv = getattr(ctx, "_ghost_autohammer_interval", 10.0)
            logger.info(f"Ghost auto-hammer test ON: simulating an inbound "
                        f"hammer hit every {iv:.0f}s. Hold your hammer charge "
                        f"to exercise the mid-swing case.")
        else:
            logger.info("Ghost auto-hammer test OFF.")

    def _ghost_names(self, mode: str = "toggle"):
        """Toggle ghost name tags. Affects both what you see (other
        players' name tags above their ghosts) and what others see of
        you (your name tag above your ghost on their screens). Defaults
        ON each session; not persisted across reconnect.

        Usage: /ghost_names         - toggle current state
               /ghost_names on      - force on
               /ghost_names off     - force off
        """
        ctx = self.ctx
        m = (mode or "toggle").strip().lower()
        cur_hidden = getattr(ctx, "_ghost_names_hidden", False)
        if m in ("on", "show", "1", "true"):
            new_hidden = False
        elif m in ("off", "hide", "0", "false"):
            new_hidden = True
        elif m in ("toggle", "t", ""):
            new_hidden = not cur_hidden
        else:
            logger.info(f"ghost_names: unknown mode '{mode}'. Use on/off/toggle.")
            return

        ctx._ghost_names_hidden = new_hidden

        try:
            vlink_force_presence(ctx)
        except Exception:
            pass

        logger.info(f"Ghost name tags {'OFF' if new_hidden else 'ON'} "
                    f"(both your view and peers' view of you).")

    def _ghost_team(self, *args):
        """Set, clear, or query your team membership. Teams are local to
        this AP team's visibility scope (you only see/hit peers on your
        AP team to begin with). Same-team peers don't hammer each other
        unless friendly fire is enabled (/ghost_friendly_fire).

        Defaults to no team each session; not persisted across reconnect.

        Usage: /ghost_team join <color>  - join red/blue/green/yellow
               /ghost_team leave         - clear your team
               /ghost_team status        - show your team + FF state
               /ghost_team list          - show all visible peers' teams
        """
        ctx = self.ctx
        if not args:
            self._ghost_team_status()
            return

        sub = args[0].strip().lower()
        if sub in ("join", "j", "set"):
            if len(args) < 2:
                logger.info("ghost_team: usage: /ghost_team join <red|blue|green|yellow>")
                return
            color = args[1].strip().lower()
            team_id = Ghosts.TEAM_NAMES.get(color)
            if team_id is None or team_id == Ghosts.TEAM_NONE:
                logger.info(f"ghost_team: unknown color '{color}'. "
                            f"Use red, blue, green, or yellow.")
                return
            ctx._ghost_team_id = team_id
            label = Ghosts.TEAM_LABELS.get(team_id, str(team_id))
            logger.info(f"Joined team {label}.")
            try:
                vlink_force_presence(ctx)
            except Exception:
                pass

        elif sub in ("leave", "l", "clear", "none"):
            ctx._ghost_team_id = Ghosts.TEAM_NONE
            logger.info("Left team. You are no longer aligned.")
            try:
                vlink_force_presence(ctx)
            except Exception:
                pass

        elif sub in ("status", "s", "?"):
            self._ghost_team_status()

        elif sub in ("list", "ls"):
            self._ghost_team_list()

        else:
            logger.info(f"ghost_team: unknown subcommand '{sub}'. "
                        f"Use join/leave/status/list.")

    def _ghost_team_status(self):
        ctx = self.ctx
        team_id = int(getattr(ctx, "_ghost_team_id", Ghosts.TEAM_NONE))
        ff = bool(getattr(ctx, "_ghost_friendly_fire", False))
        label = Ghosts.TEAM_LABELS.get(team_id, "(unknown)")
        if team_id == Ghosts.TEAM_NONE:
            logger.info("Team: none. Friendly fire: "
                        f"{'ON' if ff else 'OFF'} (only matters with a team).")
        else:
            logger.info(f"Team: {label}. Friendly fire: {'ON' if ff else 'OFF'}.")

    def _ghost_team_list(self):
        ctx = self.ctx
        peers = getattr(ctx, "_ghost_peers", {}) or {}
        if not peers:
            logger.info("No peers visible.")
            return

        by_team = {}
        for state in peers.values():
            if not isinstance(state, dict):
                continue
            tid = int(state.get("team_id", 0))
            name = str(state.get("slot_name", "") or "?")
            by_team.setdefault(tid, []).append(name)

        for tid in sorted(by_team.keys()):
            label = Ghosts.TEAM_LABELS.get(tid, f"(?{tid})") or "no team"
            members = ", ".join(sorted(by_team[tid]))
            logger.info(f"  {label}: {members}")

    def _ghost_friendly_fire(self, mode: str = "toggle"):
        """Toggle friendly fire. When ON, you can hammer same-team peers
        normally. When OFF (default), same-team hits are filtered out
        on the attacker side. Per-session, not persisted.

        FF is asymmetric: only YOUR setting governs YOUR swings. If
        teammates have different FF settings, behaviors don't cancel
        out - each player's hits are filtered (or not) by their own
        flag.

        Usage: /ghost_friendly_fire        - toggle
               /ghost_friendly_fire on     - enable FF
               /ghost_friendly_fire off    - disable FF
        """
        ctx = self.ctx
        m = (mode or "toggle").strip().lower()
        cur = bool(getattr(ctx, "_ghost_friendly_fire", False))
        if m in ("on", "1", "true", "enable"):
            new = True
        elif m in ("off", "0", "false", "disable"):
            new = False
        elif m in ("toggle", "t", ""):
            new = not cur
        else:
            logger.info(f"ghost_friendly_fire: unknown mode '{mode}'. "
                        f"Use on/off/toggle.")
            return

        ctx._ghost_friendly_fire = new
        logger.info(f"Friendly fire {'ON' if new else 'OFF'}.")
        try:
            vlink_force_presence(ctx)
        except Exception:
            pass



class TTYDContext(cmmCtx):
    command_processor = TTYDCommandProcessor
    game = "Paper Mario: The Thousand-Year Door"
    tags = {"AP", Ghosts.VLINK_TAG}
    dolphin_connected: bool = False
    seed_verified: bool = False
    slot_data: dict | None = {}
    checked_locations = set()
    previous_room = None
    death_sent: bool = False

    _ghost_subscribed: bool = False
    _ghost_peers: dict = {}

    _ghost_addrs: typing.Optional[dict] = None

    def __init__(self, server_address, password):
        super().__init__(server_address, password)
        self.items_handling = 0b101

    async def server_auth(self, password_requested: bool = False):
        if password_requested and not self.password:
            await super(TTYDContext, self).server_auth(password_requested)
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
        elif cmd == "Bounced":
            data = args.get("data") or {}
            if data.get("ttyd_hit") is True:
                _on_inbound_hit(self, data)
            elif data.get(Ghosts.VLINK_KIND) is not None:
                _vlink_on_bounce(self, data)

    def on_deathlink(self, data: typing.Dict[str, typing.Any]) -> None:
        super().on_deathlink(data)
        trigger_death(self)

    async def disconnect(self, allow_autoreconnect: bool = False):
        await super().disconnect()
        self.slot = None
        self.slot_data = None
        self.team = None
        self.checked_locations = set()
        self.seed_name = None
        self.seed_verified = False
        _on_ghost_disconnect(self)

    def make_gui(self) -> "type[kvui.GameManager]":
        from kvui import GameManager
        class TTYDManager(GameManager):
            logging_pairs = [("Client", "Archipelago")]
            base_title = "Archipelago TTYD Client"
        if not _check_universal_tracker_version():
            return TTYDManager
        class TrackerManager(super().make_gui()):
            logging_pairs = [("Client", "Archipelago")]
            base_title = f"Archipelago TTYD Client with {UT_VERSION}"
        return TrackerManager

    async def receive_items(self):
        current_length = dolphin.read_word(RECEIVED_LENGTH)
        if current_length > 255:
            return
        if current_length > 0:
            return
        index = dolphin.read_word(RECEIVED_INDEX)
        if index > len(self.items_received):
            return
        items = min(len(self.items_received) - index, 255)
        if items <= 0:
            return
        item_ids = [get_rom_item_id(self.items_received[i]) for i in range(index, index + items)]
        packed_data = struct.pack(f'>{len(item_ids)}H', *item_ids)
        dolphin.write_bytes(RECEIVED_ITEM_ARRAY, packed_data)
        dolphin.write_word(RECEIVED_LENGTH, items)
        dolphin.write_word(RECEIVED_INDEX, index + items)

    async def check_ttyd_locations(self):
        locations_to_send = set()
        try:
            for location, gsw_info in location_gsw_info.items():
                gsw_type, offset, value = gsw_info
                if offset == 0:
                    continue
                if 78780850 <= location <= 78780973:
                    offset = 0x117A + location_to_unit[location][0]
                if gsw_type.value == 0:
                    if gsw_check(offset) >= value:
                        locations_to_send.add(location)
                elif gsw_type.value == 1:
                    if gswf_check(offset):
                        locations_to_send.add(location)
            if len(locations_to_send) > 0:
                self.checked_locations &= locations_to_send
                await self.send_msgs([{"cmd": 'LocationChecks', "locations": locations_to_send}])
        except Exception as e:
            logger.error(traceback.format_exc())

    async def check_death(self):
        death_byte = dolphin.read_byte(0x80003240)
        if death_byte > 1:
            return
        if death_byte == 1:
            dolphin.write_byte(0x80003240, 0)
            if not self.death_sent:
                await self.send_death(self.player_names[self.slot] + " had no life shrooms.")
            self.death_sent = False

    def save_loaded(self) -> bool:
        value = dolphin.read_byte(0x80003228)
        if value > 1:
            return False
        return value > 0
async def _run_game(rom: str):
    import os
    auto_start = settings.get_settings().ttyd_options.rom_start

    if auto_start is True:
        dolphin_path = settings.get_settings().ttyd_options.dolphin_path
        subprocess.Popen(
            [
                dolphin_path,
                f"--exec={os.path.realpath(rom)}",
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

async def ttyd_sync_task(ctx: TTYDContext):
    logger.info("Starting Dolphin connector...")
    while not ctx.exit_event.is_set():
        if dolphin.is_hooked() and ctx.dolphin_connected:
            if ctx.slot:
                try:
                    if not validate_connection():
                        logger.info("TTYD is no longer running. Disconnecting from Dolphin.")
                        dolphin.un_hook()
                        ctx.dolphin_connected = False
                        ctx.seed_verified = False
                        await asyncio.sleep(3)
                        continue
                    if not ctx.seed_verified:
                        logger.info("Checking ROM seed...")
                        seed = read_string(SEED, 0x10)
                        if seed not in ctx.seed_name:
                            await ctx.disconnect()
                            logger.info("ROM Seed does not match Room seed. Please make sure you are using the correct patch.")
                            dolphin.un_hook()
                            await asyncio.sleep(3)
                            continue
                        ctx.seed_verified = True
                        logger.info("ROM Seed verified successfully.")
                    if "DeathLink" in ctx.tags:
                        await ctx.check_death()
                    if not ctx.save_loaded():
                        await asyncio.sleep(0.5)
                        continue
                    current_room = read_string(ROOM, 6)
                    if ctx.previous_room != current_room:
                        ctx.previous_room = current_room
                        await ctx.send_msgs([{
                            "cmd": "Set",
                            "key": f"ttyd_room_{ctx.team}_{ctx.slot}",
                            "default": 0,
                            "want_reply": False,
                            "operations": [{"operation": "replace", "value": current_room}]
                        }])
                    await ctx.receive_items()
                    await ctx.check_ttyd_locations()
                    goal = ctx.slot_data.get("goal", 0)
                    if goal == 1: # Shadow Queen
                        if not ctx.finished_game and gsw_check(1708) >= 18:
                            await ctx.send_msgs([{"cmd": "StatusUpdate", "status": ClientStatus.CLIENT_GOAL}])
                    elif goal == 2: # Crystal Stars
                        star_count = dolphin.read_byte(0x8000323B)
                        if not ctx.finished_game and star_count <= 7 and star_count >= ctx.slot_data["goal_stars"]:
                            await ctx.send_msgs([{"cmd": "StatusUpdate", "status": ClientStatus.CLIENT_GOAL}])
                    else:
                        if not ctx.finished_game and gswf_check(5085):
                            await ctx.send_msgs([{"cmd": "StatusUpdate", "status": ClientStatus.CLIENT_GOAL}])
                    await asyncio.sleep(.5)
                except Exception as e:
                    logger.info(traceback.format_exc())
                    dolphin.un_hook()
                    ctx.dolphin_connected = False
                    await asyncio.sleep(1)
            else:
                await asyncio.sleep(1)
        else:
            try:
                logger.info("Attempting to connect to Dolphin...")
                dolphin.hook()
                if not dolphin.is_hooked():
                    logger.info("Connection to Dolphin failed... Attempting again")
                    ctx.dolphin_connected = False
                    await ctx.disconnect()
                    await asyncio.sleep(3)
                    continue
                if not validate_connection():
                    logger.info("Dolphin hooked but TTYD is not running. "
                                "Please load Paper Mario: The Thousand-Year Door.")
                    dolphin.un_hook()
                    ctx.dolphin_connected = False
                    await asyncio.sleep(5)
                    continue
                logger.info("Dolphin connected successfully.")
                ctx.dolphin_connected = True
            except Exception as e:
                dolphin.un_hook()
                logger.info("Connection to Dolphin failed... Attempting again")
                logger.error(traceback.format_exc())
                ctx.dolphin_connected = False
                await ctx.disconnect()
                await asyncio.sleep(3)
                continue


def trigger_death(ctx):
    """Receive a deathlink from another world: write 1 to the AP
    scratch death byte so the game kills the player on next tick."""
    try:
        dolphin.write_byte(0x80003240, 1)
    except Exception:
        logger.exception("trigger_death: write failed")


def launch(*args):
    async def main(args):
        if args.patch_file:
            await asyncio.create_task(_patch_and_run_game(args.patch_file))
        ctx = TTYDContext(args.connect, args.password)
        ctx.server_task = asyncio.create_task(server_loop(ctx), name="ServerLoop")
        if gui_enabled:
            if tracker_loaded:
                ctx.run_generator()
            ctx.run_gui()
        ctx.run_cli()
        ctx.gl_sync_task = asyncio.create_task(ttyd_sync_task(ctx), name="TTYD Sync Task")
        ctx.ghost_sync_task = asyncio.create_task(
            ttyd_ghost_sync_task(ctx), name="GhostSync")

        await ctx.exit_event.wait()
        ctx.server_address = None

        await ctx.shutdown()

    parser = get_base_parser()
    parser.add_argument("patch_file", default="", type=str, nargs="?", help="Path to an APTTYD file")
    args = parser.parse_args(args)

    import colorama

    colorama.just_fix_windows_console()
    asyncio.run(main(args))
    colorama.deinit()