import asyncio
import collections
import struct
import subprocess
import traceback
import typing
import settings
import Patch
import Utils
from CommonClient import ClientCommandProcessor, get_base_parser, gui_enabled, logger, server_loop
import dolphin_memory_engine as dolphin
from NetUtils import NetworkItem, ClientStatus, SlotType
from . import Ghosts
from .Data import location_gsw_info, location_to_unit
from .Items import items_by_id

from .ttyd_runtime import (
    _resolve_ghost_addresses,
    _drain_outbound_hits,
    _sample_spin_for_hint,
    _write_peer_block,
    _publish_self_state,
    _on_ghost_update,
    _on_ghost_disconnect,
    _subscribe_to_peers,
    _on_inbound_hit,
    _publish_match_hud,
    _clear_match_hud,
    _publish_match_to_network,
    _clear_match_from_network,
    _subscribe_to_match,
    _on_match_bounce,
    _dispatch_match_keys,
    _match_timer_task,
    ttyd_ghost_sync_task,
    MATCH_BOUNCE_EVENT,
    GHOST_TEST_DELAY_S,
    GHOST_RENDER_INTERVAL_S, GHOST_PUBLISH_INTERVAL_S,
    SOLO_BOT_SLOT_BASE, SOLO_BOT_MAX, SOLO_BOT_DEFAULT_N,
    SOLO_BOT_OFFSETS,
    _solo_default_role,
    _solo_clear_peers,
    _solo_build_match,
    _resolve_self_game_role,
    GHOST_TEST_OFFSET_X,
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

# Master toggle for the hide-and-seek subsystem. Flip to True to
# re-enable. While False:
#   - /hns and /hns_solo commands report disabled and no-op.
#   - _match_timer_task isn't started (no 1Hz conductor publish).
#   - We don't subscribe to ttyd_match_<team>.
#   - Inbound match Bounces / SetReplies are ignored.
#   - Per-tick GhostState scratch (selfFrozen, selfGameRole,
#     pendingTeleport*) is still written by _publish_ghost_state_scratch
#     but evaluates to all-zeros (no active match -> mod-side HnS
#     features stay deactivated).
# Ghost peer rendering, hammer PvP, teams, FF, and the SFX/loop sync
# subsystems are unaffected.
HNS_ENABLED = True
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


def apply_story_state(gsw_values=None, gswf_set_bits=None, gswf_clear_bits=None,
                      *, quiet: bool = False):
    """Bulk-apply GSW + GSWF writes in a single batch. Used to "fix" the
    save-file story position before an HnS round-start teleport drops
    every member into a map that wouldn't otherwise render cleanly
    (e.g., chapter not yet completed, locked door GSWF unset, NPC
    cutscene flag pending).

    Each input is optional; pass only what you need to change.

    Parameters:
      gsw_values:       dict of {index: value} for GSW (Game Switch
                        Word). Index 0 is the 32-bit world-state
                        word; indices 1+ are 8-bit per-chapter or
                        per-event values.
      gswf_set_bits:    iterable of GSWF bit numbers to set to 1.
      gswf_clear_bits:  iterable of GSWF bit numbers to clear to 0.
      quiet:            if True, suppress the per-call summary log.

    Returns: a tuple (n_gsw_written, n_gswf_set, n_gswf_cleared,
    n_failures). Failures don't raise — they're logged and counted.
    Useful so the caller can decide whether to surface a warning
    when partial application happened (e.g., Dolphin disconnected
    mid-batch).

    Example — pin to "post-chapter-2 in Rogueport, doors unlocked":
        apply_story_state(
            gsw_values={0: 0x0F},
            gswf_set_bits=[1234, 1235, 1240],
            gswf_clear_bits=[1500],
        )
    """
    n_gsw = 0
    n_set = 0
    n_clear = 0
    n_fail = 0

    if gsw_values:
        for idx, val in gsw_values.items():
            try:
                gsw_set(int(idx), int(val))
                n_gsw += 1
            except Exception:
                logger.exception(f"apply_story_state: GSW[{idx}] = {val} failed")
                n_fail += 1

    if gswf_set_bits:
        for bit in gswf_set_bits:
            try:
                if gswf_set(int(bit)) is not False:
                    n_set += 1
                else:
                    n_fail += 1
            except Exception:
                logger.exception(f"apply_story_state: GSWF set bit {bit} failed")
                n_fail += 1

    if gswf_clear_bits:
        for bit in gswf_clear_bits:
            try:
                if gswf_clear(int(bit)) is not False:
                    n_clear += 1
                else:
                    n_fail += 1
            except Exception:
                logger.exception(f"apply_story_state: GSWF clear bit {bit} failed")
                n_fail += 1

    if not quiet:
        logger.info(
            f"apply_story_state: {n_gsw} GSW written, "
            f"{n_set} GSWF set, {n_clear} GSWF cleared"
            + (f", {n_fail} failed" if n_fail else "")
        )
    return (n_gsw, n_set, n_clear, n_fail)
def _strip_anim_suffix(name: str) -> str:
    """TTYD's animation names have suffixes encoding facing direction:
    M_S_1   = standing, front-facing
    M_S_1R  = standing, rear (back-facing)
    M_W_1L  = walking, left-facing variant
    These suffixes refer to which AGB file the animation lives in.
    Stripping them gives the base name that exists in the default AGB.
    Side effect: the ghost will always play the front-facing variant
    even when the source player is facing away. That's a known limitation
    of the single-AGB approach we're using."""

    while name and name[-1] in "LRW":
        name = name[:-1]
    return name


class TTYDCommandProcessor(ClientCommandProcessor):
    def __init__(self, ctx):
        super().__init__(ctx)


    def _cmd_ghost(self, *args):
        """Manage ghost peer settings.

        Subcommands:
          /ghost test                      - toggle single-client loopback
          /ghost names [on|off|toggle]     - hide/show your name tag
          /ghost friendly_fire [on|off]    - toggle FF for your hammer
          /ghost team join <color>         - join red/blue/green/yellow
          /ghost team leave                - clear team membership
          /ghost team status               - show your team / FF state
          /ghost team list                 - list all peers grouped by team
        """
        if not args:
            logger.info("ghost: subcommands - test / names / friendly_fire / team")
            return
        sub = args[0].strip().lower()
        rest = args[1:]
        if sub == "test":
            self._ghost_test()
        elif sub == "names":
            self._ghost_names(*rest)
        elif sub in ("friendly_fire", "ff"):
            self._ghost_friendly_fire(*rest)
        elif sub == "team":
            self._ghost_team(*rest)
        else:
            logger.info(f"ghost: unknown subcommand '{sub}'. "
                        f"Use test/names/friendly_fire/team.")

    def _cmd_hns(self, *args):
        """Hide-and-seek match commands.

        Match management:
          /hns start                     - begin a match
          /hns stop                      - end the current match early
          /hns status                    - show the current match state
          /hns leave                     - opt out of the next match
          /hns join                      - clear your opt-out flag

        Configuration (last-write-wins via DataStorage):
          /hns set <key> <value>         - change a setting
          /hns settings                  - show current settings
          /hns maps add <map>            - add a map to the pool
          /hns maps remove <map>         - remove a map
          /hns maps list                 - list maps
          /hns maps clear                - empty the pool

        Display & debug:
          /hns hud [on|off|toggle]       - toggle the in-game HUD overlay
          /hns role [none|hider|seeker]  - debug game_role byte override
          /hns solo start [N]            - solo bot test mode (N bots)
          /hns solo stop                 - tear down solo
          /hns solo list                 - show solo bots
          /hns solo role <slot> <role>   - set a solo bot's role
        """
        if not HNS_ENABLED:
            logger.info("hns: hide-and-seek is disabled in this build. "
                        "Set HNS_ENABLED=True in TTYDClient.py to re-enable.")
            return
        ctx = self.ctx
        if not args:
            self._hns_status()
            return
        sub = args[0].strip().lower()
        rest = args[1:]
        if sub == "start":
            self._hns_start()
        elif sub == "stop":
            self._hns_stop()
        elif sub in ("status", "info", "?"):
            self._hns_status()
        elif sub == "leave":
            self._hns_leave()
        elif sub == "join":
            self._hns_join()
        elif sub == "set":
            self._hns_set(*rest)
        elif sub == "settings":
            self._hns_settings()
        elif sub == "maps":
            self._hns_maps(*rest)
        elif sub == "hud":
            self._hns_hud(*rest)
        elif sub == "role":
            self._hns_role(*rest)
        elif sub == "solo":
            self._hns_solo(*rest)
        elif sub == "debug":
            self._hns_debug()
        elif sub == "next":
            self._hns_next()
        elif sub == "map":
            self._hns_map(*rest)
        elif sub == "story":
            self._hns_story(*rest)
        elif sub == "play_sfx":
            self._hns_play_sfx(*rest)
        elif sub == "mario_state":
            self._hns_mario_state()
        else:
            logger.info(f"hns: unknown subcommand '{sub}'. "
                        f"See /help hns or use start/stop/status/leave/join/"
                        f"set/settings/maps/hud/role/solo/debug/next/story/play_sfx/mario_state.")


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

    def _ghost_test(self):
        """Toggle the single-player ghost loopback test."""
        ctx = self.ctx
        ctx._ghost_loopback_active = not getattr(ctx, "_ghost_loopback_active", False)

        # Reset the position-delay buffer; it's only used when
        # GHOST_TEST_DELAY_S > 0 but cheap to clear unconditionally.
        ctx._loopback_delay_buf = collections.deque()

        if ctx._ghost_loopback_active:
            if GHOST_TEST_DELAY_S > 0.0:
                logger.info(f"Ghost loopback test ON. A translucent ghost should "
                            f"appear ~{GHOST_TEST_OFFSET_X:.0f} units to your right "
                            f"and trail your actions by {GHOST_TEST_DELAY_S:.1f}s.")
            else:
                logger.info(f"Ghost loopback test ON. A translucent ghost should "
                            f"appear ~{GHOST_TEST_OFFSET_X:.0f} units to your right, "
                            f"mirroring your actions in real time. The ghost rides "
                            f"the same publish path as real peers, so its motion "
                            f"reflects real-AP smoothness (20Hz publish + mod-side "
                            f"60Hz lerp).")
        else:
            logger.info("Ghost loopback test OFF.")
            # Drop any synthetic loopback peer from the local table so
            # the next _write_peer_block doesn't repaint a stale ghost.
            getattr(ctx, "_ghost_peers", {}).pop(Ghosts.ghost_key(0, 99), None)

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
            asyncio.create_task(_publish_self_state(ctx))
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
                asyncio.create_task(_publish_self_state(ctx))
            except Exception:
                pass

        elif sub in ("leave", "l", "clear", "none"):
            ctx._ghost_team_id = Ghosts.TEAM_NONE
            logger.info("Left team. You are no longer aligned.")
            try:
                asyncio.create_task(_publish_self_state(ctx))
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
            asyncio.create_task(_publish_self_state(ctx))
        except Exception:
            pass

    def _hns_solo(self, *args):
        """Solo test mode: spawn synthetic bot peers next to your
        player and seat them as members of a local lobby. Lets you
        verify the v27 game_role byte (and, once the phase machine
        lands, the full hide-and-seek flow) without needing a second
        connected client.

        Bots are local-only - they aren't published to AP, so other
        connected players don't see them. They occupy ghost slots
        91..95 (5 bots max). Each bot has its own toggleable
        game_role byte that controls its name-tag color: red for
        seeker, green for hider, palette for none.

        Usage:
            /hns_solo                          - show solo state
            /hns_solo start [num_bots]         - start with N bots (default 3, max 5)
            /hns_solo stop                     - tear down
            /hns_solo list                     - show bots and their roles
            /hns_solo role <slot> <none|hider|seeker>
                                               - override a bot's role
        """
        ctx = self.ctx
        if not args:
            self._hns_solo_status()
            return
        sub = args[0].strip().lower()
        if sub == "start":
            self._hns_solo_start(*args[1:])
        elif sub == "stop":
            self._hns_solo_stop()
        elif sub == "list":
            self._hns_solo_status()
        elif sub == "role":
            self._hns_solo_role(*args[1:])
        else:
            logger.info(f"hns_solo: unknown subcommand '{sub}'. "
                        f"Use start/stop/list/role.")

    def _hns_solo_status(self):
        ctx = self.ctx
        bots = getattr(ctx, "_solo_bots", None) or []
        if not bots:
            logger.info("hns_solo: not active. /hns_solo start [N] to begin.")
            return
        logger.info(f"hns_solo: {len(bots)} bot(s) active:")
        for bot in bots:
            label = Ghosts.GAME_ROLE_LABELS.get(
                bot.get("game_role", Ghosts.GAME_ROLE_NONE), "") or "none"
            logger.info(f"  slot {bot['slot']:2d}: {bot['name']} [{label}]")

    def _hns_solo_start(self, *args):
        ctx = self.ctx
        if getattr(ctx, "_solo_bots", None):
            logger.info("hns_solo: already active. /hns_solo stop first.")
            return
        if ctx.slot is None or ctx.team is None:
            logger.info("hns_solo: connect to AP first (need a slot id).")
            return
        if getattr(ctx, "_solo_bots", None):
            logger.info("hns_solo: solo mode is already running. /hns solo stop first.")
            return
        cur_match = getattr(ctx, "_match", None)
        if cur_match is not None and cur_match.is_active():
            logger.info("hns_solo: a real match is already running. /hns stop first.")
            return

        n = SOLO_BOT_DEFAULT_N
        if args:
            try:
                n = int(args[0])
            except ValueError:
                logger.info(f"hns_solo: '{args[0]}' is not a number.")
                return
        n = max(1, min(SOLO_BOT_MAX, n))

        bots = []
        for i in range(n):
            bots.append({
                "slot":      SOLO_BOT_SLOT_BASE + i,
                "name":      f"Bot{i+1}",
                "game_role": _solo_default_role(i, n),
                "offset":    SOLO_BOT_OFFSETS[i],
            })
        ctx._solo_bots = bots

        ctx._match = _solo_build_match(ctx, n)
        if not ctx._match.settings.map_pool:
            try:
                cur = read_string(ROOM, 16) or ""
                if cur:
                    ctx._match.settings.map_pool = [cur]
            except Exception:
                pass

        logger.info(f"hns_solo: started with {n} bot(s) (slots "
                    f"{SOLO_BOT_SLOT_BASE}..{SOLO_BOT_SLOT_BASE + n - 1}).")
        logger.info("hns_solo: you're the seeker (red, frozen during HIDE); "
                    "all bots are hiders (green).")
        logger.info(f"hns_solo: round 1 of {ctx._match.settings.round_count}, "
                    f"hide {ctx._match.settings.hide_phase_seconds}s -> "
                    f"seek {ctx._match.settings.round_time_limit_seconds}s.")
        logger.info("hns_solo: use '/hns_solo role <slot> <role>' to change a bot's role.")

        # Kick a publish so bot peers appear immediately and the HUD
        # reflects the new lobby state without waiting for the next tick.
        try:
            asyncio.create_task(_publish_self_state(ctx))
        except Exception:
            pass
        try:
            asyncio.create_task(_publish_match_hud(ctx))
        except Exception:
            pass

    def _hns_solo_stop(self):
        ctx = self.ctx
        if not getattr(ctx, "_solo_bots", None):
            logger.info("hns_solo: not active.")
            return
        ctx._solo_bots = []
        _solo_clear_peers(ctx)
        st = getattr(ctx, "_match", None)
        if st is not None:
            st.status = Ghosts.MATCH_STATUS_IDLE
            st.timer_seconds = 0
            st.members = []
            st.game_state = {}
            st.conductor_slot = 0
        logger.info("hns_solo: stopped, bots removed.")
        try:
            asyncio.create_task(_publish_match_hud(ctx))
        except Exception:
            pass

    def _hns_solo_role(self, *args):
        ctx = self.ctx
        bots = getattr(ctx, "_solo_bots", None) or []
        if not bots:
            logger.info("hns_solo: not active.")
            return
        if len(args) < 2:
            logger.info("hns_solo: usage: /hns_solo role <slot> <none|hider|seeker>")
            return
        try:
            target_slot = int(args[0])
        except ValueError:
            logger.info(f"hns_solo: slot '{args[0]}' is not a number.")
            return
        role_name = args[1].strip().lower()
        role = Ghosts.GAME_ROLE_NAMES.get(role_name)
        if role is None:
            logger.info(f"hns_solo: unknown role '{role_name}'. "
                        f"Use none/hider/seeker.")
            return
        for bot in bots:
            if bot["slot"] == target_slot:
                bot["game_role"] = role
                label = Ghosts.GAME_ROLE_LABELS.get(role, "") or "none"
                logger.info(f"hns_solo: bot slot {target_slot} -> {label}.")
                # Force-republish so the new tag color shows immediately.
                try:
                    asyncio.create_task(_publish_self_state(ctx))
                except Exception:
                    pass
                return
        logger.info(f"hns_solo: no bot at slot {target_slot}. /hns_solo list.")

    # ----- HnS match helpers (called from /hns dispatcher) -----

    def _hns_next(self):
        """Conductor-only debug: fast-forward the current phase.

        HIDE        -> SEEK   (skip the hide countdown)
        SEEK        -> ROUND_OVER (mark round ended early)
        ROUND_OVER  -> next round HIDE (or MATCH_END if last round)
        MATCH_END   -> IDLE  (reset to no-match state)

        Useful for testing teleport / freeze without waiting through
        full timer durations."""
        ctx = self.ctx
        st = getattr(ctx, "_match", None)
        if st is None or not st.is_active():
            logger.info("hns next: no active match.")
            return

        # If we're the local match owner, apply directly.
        # Otherwise forward via Bounce — the owner will run the
        # transition and republish; we'll see the new state on the
        # next SetReply.
        if st.is_conductor():
            st.timer_seconds = 0
            from .ttyd_runtime import _on_match_timer_zero
            _on_match_timer_zero(ctx, st)
            new_label = Ghosts.MATCH_STATUS_LABELS.get(st.status, "?")
            new_round = (st.game_state or {}).get("round", "?")
            new_map   = (st.game_state or {}).get("current_map", "")
            logger.info(f"hns next: advanced -> {new_label}"
                        + (f", round {new_round}" if new_label in ("Hide","Seek","Round Over") else "")
                        + (f", map {new_map}" if new_map else ""))
            self._publish_match_now()
        else:
            self._forward_match_command(kind="next")
            logger.info("hns next: forwarded to match owner.")

    def _hns_play_sfx(self, *args):
        """Debug: fire psndSFXOn(<id>) on the local Mario.

        Usage:
          /hns play_sfx <id> [3d]

        <id> accepts hex (`0x1013`, `0X1013`) or decimal (`4115`).
        Adding the literal `3d` token routes the call through
        psndSFXOn_3D anchored at Mario's position; otherwise the
        plain (2D) variant is used.

        The mod's psndSFXOn hook captures the call into
        OnLocalSfxFired, which means the sound also propagates to
        peers whenever the id passes the SfxIsAllowed whitelist.
        Useful for probing SFX_TABLE.csv ids and confirming whether
        a given id is the right boat / water / ambient sound."""
        ctx = self.ctx
        if not args:
            logger.info("hns play_sfx: usage: /hns play_sfx <id> [3d]")
            return
        raw = args[0].strip()
        try:
            sfx_id = int(raw, 0) if raw.lower().startswith("0x") else int(raw)
        except ValueError:
            logger.info(f"hns play_sfx: '{raw}' is not a valid id (use 0x.. or decimal).")
            return
        if not (0 < sfx_id <= 0xFFFFFFFF):
            logger.info(f"hns play_sfx: id {sfx_id} out of range.")
            return
        flags = 0
        for tok in args[1:]:
            if tok.strip().lower() == "3d":
                flags |= 0x01

        addrs = getattr(ctx, "_ghost_addrs", None)
        if not addrs:
            logger.info("hns play_sfx: GhostState not resolved yet (load a save first).")
            return
        try:
            dolphin.write_bytes(addrs["debug_sfx_id"],
                                int(sfx_id).to_bytes(4, "big"))
            dolphin.write_byte(addrs["debug_sfx_flags"], flags & 0xFF)
            cur_seq = dolphin.read_byte(addrs["debug_sfx_seq"])
            new_seq = (cur_seq + 1) & 0xFF
            dolphin.write_byte(addrs["debug_sfx_seq"], new_seq)
        except Exception:
            logger.exception("hns play_sfx: write failed")
            return
        variant = "psndSFXOn_3D" if (flags & 0x01) else "psndSFXOn"
        logger.info(f"hns play_sfx: queued {variant}(0x{sfx_id:X}) "
                    f"(seq {cur_seq} -> {new_seq}). Listen / watch peers.")

    def _hns_mario_state(self):
        """Diagnostic: snapshot the current Mario player-struct fields
        Python reads in `_read_self_state`, plus the mod's published
        `selfPaperAgbName` scratch. Used to inspect what the engine
        is doing during odd states (e.g. the Vivian-rising phase
        where the receiver's paper anim doesn't replay correctly).

        Run it at the moments you care about — e.g. mid-sink, held,
        right before the rise starts, during the rise, after the
        jump-out — and compare values to see which motion_id /
        motion_timer / anim transitions the rising actually goes
        through."""
        ctx = self.ctx
        try:
            try:
                from .ttyd_runtime import MARIO_PTR_ADDR as mario_ptr_addr
            except Exception:
                mario_ptr_addr = 0x8041E900

            player_ptr = int.from_bytes(
                dolphin.read_bytes(mario_ptr_addr, 4), "big")
            if not (0x80000000 <= player_ptr < 0x81800000):
                logger.info(f"hns mario_state: player_ptr=0x{player_ptr:08X} out of range "
                            "(save not loaded?)")
                return

            buf = dolphin.read_bytes(player_ptr, 0x2D8)
            import struct as _s
            (flags1,) = _s.unpack_from(">I", buf, 0x00)
            (flags2,) = _s.unpack_from(">I", buf, 0x04)
            (flags3,) = _s.unpack_from(">I", buf, 0x0C)
            anim_ptr  = int.from_bytes(buf[0x18:0x1C], "big")
            paper_ptr = int.from_bytes(buf[0x1C:0x20], "big")
            (motion_timer,) = _s.unpack_from(">H", buf, 0x28)
            (motion_id,)    = _s.unpack_from(">H", buf, 0x2E)
            (mp_2d3,)       = _s.unpack_from(">b", buf, 0x2D3)

            anim_name = ""
            if 0x80000000 <= anim_ptr < 0x81800000:
                raw = dolphin.read_bytes(anim_ptr, 16)
                anim_name = raw.split(b"\x00", 1)[0].decode("ascii", errors="replace")
            paper_anim = ""
            if 0x80000000 <= paper_ptr < 0x81800000:
                raw = dolphin.read_bytes(paper_ptr, 16)
                paper_anim = raw.split(b"\x00", 1)[0].decode("ascii", errors="replace")

            paper_agb = ""
            try:
                addrs = getattr(ctx, "_ghost_addrs", None)
                if addrs is not None:
                    agb_addr = addrs.get("self_paper_agb")
                    if agb_addr is not None:
                        raw = dolphin.read_bytes(agb_addr, 32)
                        paper_agb = raw.split(b"\x00", 1)[0].decode(
                            "ascii", errors="replace")
            except Exception:
                pass

            logger.info("hns mario_state:")
            logger.info(f"  motion_id     = 0x{motion_id:04X} ({motion_id})")
            logger.info(f"  motion_timer  = 0x{motion_timer:04X} ({motion_timer})")
            logger.info(f"  anim          = {anim_name!r}")
            logger.info(f"  paper_anim    = {paper_anim!r}")
            logger.info(f"  paper_agb     = {paper_agb!r}  (mod-published)")
            logger.info(f"  flags1        = 0x{flags1:08X}")
            logger.info(f"  flags2        = 0x{flags2:08X}")
            logger.info(f"  flags3        = 0x{flags3:08X}")
            logger.info(f"  mp[0x2D3]     = {mp_2d3} (signed; M_W_6 paper time field)")
        except Exception:
            logger.exception("hns mario_state: read failed")

    def _hns_debug(self):
        """Diagnostic: read back v28/v29 GhostState scratch from Dolphin
        RAM and report what the mod sees vs what Python intends to write.

        If Python's `intended` values match the `dolphin` values, the
        wire is healthy and any teleport/freeze problem is mod-side.
        If they diverge, Python's writes aren't landing where the mod
        is reading — likely an offset / version mismatch."""
        ctx = self.ctx
        st = getattr(ctx, "_match", None)

        addrs = getattr(ctx, "_ghost_addrs", None)
        if not _resolve_ghost_addresses(ctx):
            logger.info("hns debug: GhostState pointer not yet resolved "
                        "(connect to AP + load TTYD first).")
            return
        addrs = ctx._ghost_addrs

        logger.info("=" * 50)
        logger.info("hns debug: GhostState scratch read-back")
        logger.info(f"  GhostState base 0x{addrs['peer_block']:08X}")
        logger.info(f"  Wire format VERSION = {Ghosts.VERSION}")
        logger.info("")

        try:
            role  = dolphin.read_byte(addrs["self_game_role"])
            froz  = dolphin.read_byte(addrs["self_frozen"])
            tseq  = dolphin.read_byte(addrs["pending_teleport_seq"])
            tmap  = dolphin.read_bytes(addrs["pending_teleport_map"], 16)
            tbero = dolphin.read_bytes(addrs["pending_teleport_bero"], 16)
        except Exception as e:
            logger.info(f"hns debug: scratch read failed: {e}")
            return

        tmap_str  = tmap.split(b"\x00", 1)[0].decode("ascii", errors="replace")
        tbero_str = tbero.split(b"\x00", 1)[0].decode("ascii", errors="replace")

        logger.info("Dolphin RAM (what the MOD sees):")
        logger.info(f"  selfGameRole       (0x{addrs['self_game_role']:08X}) = {role}  "
                    f"({Ghosts.GAME_ROLE_LABELS.get(role, '?') or 'none'})")
        logger.info(f"  selfFrozen         (0x{addrs['self_frozen']:08X}) = {froz}")
        logger.info(f"  pendingTeleportSeq (0x{addrs['pending_teleport_seq']:08X}) = {tseq}")
        logger.info(f"  pendingTeleportMap (0x{addrs['pending_teleport_map']:08X}) = "
                    f"{tmap_str!r}")
        logger.info(f"  pendingTeleportBero(0x{addrs['pending_teleport_bero']:08X}) = "
                    f"{tbero_str!r}")
        logger.info("")

        logger.info("Python state (what we INTEND to write):")
        if st is None:
            logger.info("  ctx._match: None (no AP connection?)")
        else:
            self_role = _resolve_self_game_role(ctx)
            logger.info(f"  match.status      = {Ghosts.MATCH_STATUS_LABELS.get(st.status, '?')}")
            logger.info(f"  match.is_active() = {st.is_active()}")
            logger.info(f"  local match owner = {st.is_conductor()}")
            logger.info(f"  resolved my role  = {Ghosts.GAME_ROLE_LABELS.get(self_role, '?') or 'none'}")
            gs = st.game_state or {}
            logger.info(f"  game_state.map_seq      = {gs.get('map_seq')}")
            logger.info(f"  game_state.current_map  = {gs.get('current_map')!r}")
            logger.info(f"  game_state.current_bero = {gs.get('current_bero')!r}")
            logger.info(f"  ctx._last_applied_map_seq = "
                        f"{getattr(ctx, '_last_applied_map_seq', None)}")
            logger.info(f"  ctx._local_teleport_seq   = "
                        f"{getattr(ctx, '_local_teleport_seq', None)}")
        logger.info("=" * 50)
        logger.info("If the Dolphin map is empty/garbage, Python isn't writing.")
        logger.info("If it shows your map but the world isn't loading, the mod's")
        logger.info("seqSetSeq call is firing but TTYD is rejecting it (probably")
        logger.info("needs a real bero name). Use /hns set bero <name> as a workaround.")

    def _hns_status(self):
        ctx = self.ctx
        st = getattr(ctx, "_match", None)
        if st is None:
            logger.info("Not connected to AP yet (no match state).")
            return
        status_label = Ghosts.MATCH_STATUS_LABELS.get(st.status, "?")
        logger.info(f"Match (team {st.team}): {status_label}")
        if st.timer_seconds > 0:
            logger.info(f"  Timer: {st.timer_seconds}s")
        if st.is_active():
            gs = st.game_state or {}
            logger.info(f"  Round: {gs.get('round', '?')}/{gs.get('round_total', '?')}")
            cur_map = gs.get("current_map")
            if cur_map:
                logger.info(f"  Map: {cur_map}")
            roles = gs.get("members_role") or {}
            logger.info(f"  Members:")
            for m in st.members:
                role = roles.get(m.slot) or roles.get(str(m.slot)) or ""
                tag = f" [{role}]" if role else ""
                logger.info(f"    {m.name}{tag}")
        else:
            logger.info("  Run /hns start to begin a match.")

    def _hns_start(self):
        ctx = self.ctx
        st = getattr(ctx, "_match", None)
        if st is None:
            logger.info("hns: not connected to AP.")
            return
        if st.is_active():
            logger.info(f"hns: a match is already in progress "
                        f"({Ghosts.MATCH_STATUS_LABELS.get(st.status)}).")
            return
        if not st.settings.map_pool:
            logger.info("hns: cannot start - map pool is empty. "
                        "/hns maps add <map> first.")
            return
        # Need at least 2 members (us + 1 peer).
        team_peers = sum(
            1 for k in (getattr(ctx, "_ghost_peers", {}) or {})
            if k.startswith(Ghosts.KEY_PREFIX)
        )
        if team_peers < 1:
            logger.info("hns: cannot start - no other peers visible. "
                        "Wait for at least one teammate to connect.")
            return

        # Conductor begins the match.
        from .ttyd_runtime import _begin_match
        _begin_match(ctx, st)
        logger.info(f"hns: match started. Round 1/{st.settings.round_count}, "
                    f"map={st.game_state.get('current_map')}, "
                    f"hide phase {st.timer_seconds}s.")
        self._publish_match_now()

    def _hns_stop(self):
        ctx = self.ctx
        st = getattr(ctx, "_match", None)
        if st is None or not st.is_active():
            logger.info("hns: no active match.")
            return
        if st.is_conductor():
            st.status = Ghosts.MATCH_STATUS_IDLE
            st.timer_seconds = 0
            st.members = []
            st.game_state = {}
            # Keep st.conductor_slot intact so the post-stop publish
            # passes _publish_match_to_network's is_conductor() gate.
            # Without this the IDLE state never reaches non-owner
            # clients and their HUDs stay stuck on the previous phase.
            # Also lets /hns set keep working between matches; the
            # next /hns start re-runs _begin_match which sets it.
            logger.info("hns: match ended.")
            self._publish_match_now()
        else:
            self._forward_match_command(kind="stop")
            logger.info("hns: stop forwarded to match owner.")

    def _hns_leave(self):
        ctx = self.ctx
        st = getattr(ctx, "_match", None)
        if st is None:
            logger.info("hns: not connected to AP.")
            return
        slot = int(getattr(ctx, "slot", 0) or 0)
        if slot in st.opted_out:
            logger.info("hns: already opted out.")
            return
        if st.is_conductor():
            st.opted_out.append(slot)
            logger.info("hns: opted out of the next match. /hns join to re-enter.")
            self._publish_match_now()
        else:
            self._forward_match_command(kind="leave", extra={"slot": slot})
            logger.info("hns: opt-out forwarded. You'll be excluded from "
                        "the next match. /hns join to re-enter.")

    def _hns_join(self):
        ctx = self.ctx
        st = getattr(ctx, "_match", None)
        if st is None:
            logger.info("hns: not connected to AP.")
            return
        slot = int(getattr(ctx, "slot", 0) or 0)
        if slot not in st.opted_out:
            logger.info("hns: not opted out (already eligible).")
            return
        if st.is_conductor():
            st.opted_out.remove(slot)
            logger.info("hns: opted in. You'll be included in the next match.")
            self._publish_match_now()
        else:
            self._forward_match_command(kind="join", extra={"slot": slot})
            logger.info("hns: opt-in forwarded. You'll be included in "
                        "the next match.")

    def _hns_set(self, *args):
        ctx = self.ctx
        st = getattr(ctx, "_match", None)
        if st is None:
            logger.info("hns: not connected to AP.")
            return
        if st.is_active():
            logger.info("hns: settings are frozen during an active match.")
            return
        if len(args) < 2:
            logger.info("hns: usage: /hns set <key> <value>. "
                        "Keys: " + ", ".join(sorted(Ghosts.LOBBY_SETTING_BOUNDS.keys())
                                              if hasattr(Ghosts, "LOBBY_SETTING_BOUNDS")
                                              else Ghosts.MATCH_SETTING_BOUNDS.keys()))
            return
        key = args[0].strip().lower()
        raw = " ".join(args[1:]).strip()
        try:
            value = Ghosts.parse_setting_value(key, raw)
        except ValueError as e:
            logger.info(f"hns: {e}")
            return
        setattr(st.settings, key, value)
        logger.info(f"hns: setting '{key}' = {value}.")
        self._publish_match_now()

    def _hns_settings(self):
        ctx = self.ctx
        st = getattr(ctx, "_match", None)
        if st is None:
            logger.info("hns: not connected to AP.")
            return
        s = st.settings
        logger.info(f"Match settings (team {st.team}):")
        logger.info(f"  round_count              = {s.round_count}")
        logger.info(f"  hide_phase_seconds       = {s.hide_phase_seconds}")
        logger.info(f"  round_time_limit_seconds = {s.round_time_limit_seconds}")
        logger.info(f"  seeker_count_threshold   = {s.seeker_count_threshold} "
                    f"(=> {Ghosts.compute_seeker_count(len(st.members) or 4, s.seeker_count_threshold)} "
                    f"seeker(s) at member count)")
        if s.map_pool:
            logger.info(f"  map_pool ({len(s.map_pool)}): {', '.join(s.map_pool)}")
        else:
            logger.info(f"  map_pool: (empty - /hns maps add <map> first)")

    def _hns_maps(self, *args):
        """Manage the round map pool.

        /hns maps add <name>           - add a verified BUILTIN_MAPS
                                          entry by short name
                                          (rogueport, petalburg, ...).
                                          Rejects unverified map:bero
                                          pairs that would crash on load.
        /hns maps add_raw <map>:<bero> - bypass the builtin check; lets
                                          you add unverified pairs for
                                          testing. Caveat emptor.
        /hns maps remove <entry>       - remove by exact pool entry or
                                          builtin short name
        /hns maps list                 - show pool
        /hns maps clear                - empty the pool
        /hns maps builtins             - list available builtin names
        """
        ctx = self.ctx
        st = getattr(ctx, "_match", None)
        if st is None:
            logger.info("hns: not connected to AP.")
            return
        if not args:
            logger.info("hns: usage: /hns maps add <name> | add_raw <map>:<bero> | remove <entry> | list | clear | builtins")
            return
        sub = args[0].strip().lower()
        s = st.settings
        if sub == "list":
            if s.map_pool:
                logger.info(f"Map pool ({len(s.map_pool)}): {', '.join(s.map_pool)}")
            else:
                logger.info("Map pool is empty. /hns maps builtins for available presets.")
            return
        if sub == "builtins":
            logger.info(f"Builtin map presets ({len(Ghosts.BUILTIN_MAPS)}):")
            for short, (mp, br) in sorted(Ghosts.BUILTIN_MAPS.items()):
                br_disp = br if br else "(default spawn)"
                logger.info(f"  {short:18s} -> {mp}:{br_disp}")
            return
        if st.is_active():
            logger.info("hns: map pool is frozen during an active match.")
            return
        if sub == "add":
            if len(args) < 2:
                logger.info("hns: usage: /hns maps add <name>")
                return
            raw = " ".join(args[1:]).strip()
            entry = Ghosts.resolve_map_entry(raw)
            if entry is None or not entry[0]:
                logger.info(f"hns: '{raw}' isn't a builtin name "
                            f"(see /hns maps builtins) or a valid map:bero pair.")
                return
            map_id, bero = entry
            # Restrict /hns maps add to verified BUILTIN_MAPS rows only.
            # Unverified map:bero pairs can soft-lock or crash the engine
            # on load; use /hns maps add_raw to bypass when testing.
            if (map_id, bero) not in set(Ghosts.BUILTIN_MAPS.values()):
                logger.info(f"hns: '{raw}' isn't a verified builtin "
                            f"(see /hns maps builtins). Use "
                            f"/hns maps add_raw <map>:<bero> to add "
                            f"an unverified pair anyway.")
                return
            stored = Ghosts.encode_map_pool_entry(map_id, bero)
            if stored in s.map_pool:
                logger.info(f"hns: '{stored}' already in pool.")
                return
            s.map_pool.append(stored)
            preset_note = f" (from preset '{raw}')" if raw in Ghosts.BUILTIN_MAPS else ""
            logger.info(f"hns: added '{stored}'{preset_note}. Pool size: {len(s.map_pool)}.")
        elif sub == "add_raw":
            # Escape hatch: accepts any map:bero pair without builtin
            # verification. May crash or soft-lock on load — caveat
            # emptor. Useful for testing maps that aren't yet in the
            # curated BUILTIN_MAPS table.
            if len(args) < 2:
                logger.info("hns: usage: /hns maps add_raw <map>:<bero>")
                return
            raw = " ".join(args[1:]).strip()
            entry = Ghosts.resolve_map_entry(raw)
            if entry is None or not entry[0]:
                logger.info(f"hns: '{raw}' isn't parseable as a "
                            f"map:bero pair.")
                return
            map_id, bero = entry
            stored = Ghosts.encode_map_pool_entry(map_id, bero)
            if stored in s.map_pool:
                logger.info(f"hns: '{stored}' already in pool.")
                return
            s.map_pool.append(stored)
            logger.info(f"hns: added raw '{stored}' (unverified). "
                        f"Pool size: {len(s.map_pool)}.")
        elif sub == "remove":
            if len(args) < 2:
                logger.info("hns: usage: /hns maps remove <entry>")
                return
            name = " ".join(args[1:]).strip()
            # Allow remove by builtin short name too — resolve and
            # remove the corresponding stored entry.
            entry = Ghosts.resolve_map_entry(name)
            target = name
            if entry and entry[0]:
                target = Ghosts.encode_map_pool_entry(entry[0], entry[1])
            if target not in s.map_pool:
                logger.info(f"hns: '{name}' not in pool.")
                return
            s.map_pool.remove(target)
            logger.info(f"hns: removed '{target}'. Pool size: {len(s.map_pool)}.")
        elif sub == "clear":
            s.map_pool = []
            logger.info("hns: map pool cleared.")
        else:
            logger.info(f"hns: unknown maps subcommand '{sub}'. "
                        f"Use add/add_raw/remove/list/clear/builtins.")
            return
        self._publish_match_now()

    def _hns_map(self, *args):
        """Override the map for the next round. Conductor-only,
        valid in IDLE or between rounds (ROUND_OVER). Cleared after
        being applied — only affects one round.

        /hns map <name>      - set next-round map (builtin or map:bero)
        /hns map clear       - drop the override (next round goes
                                back to random pool pick)
        /hns map             - show the current override (if any)
        """
        ctx = self.ctx
        st = getattr(ctx, "_match", None)
        if st is None:
            logger.info("hns: not connected to AP.")
            return

        gs = st.game_state or {}
        cur_override = gs.get("next_map_override")

        if not args:
            if (isinstance(cur_override, (list, tuple)) and len(cur_override) >= 2
                    and cur_override[0]):
                br = cur_override[1] or "(default spawn)"
                logger.info(f"hns map: next-round override is {cur_override[0]}:{br}.")
            else:
                logger.info("hns map: no next-round override (random pool pick).")
            return

        if st.status not in (Ghosts.MATCH_STATUS_IDLE, Ghosts.MATCH_STATUS_ROUND_OVER):
            logger.info("hns map: can only set the next map between rounds "
                        "(ROUND_OVER) or before a match (IDLE).")
            return

        first = args[0].strip().lower()
        if first == "clear":
            if st.is_conductor():
                st.game_state.pop("next_map_override", None)
                logger.info("hns map: override cleared. Next round picks from pool.")
                self._publish_match_now()
            else:
                self._forward_match_command(kind="map_override",
                                             extra={"map_id": "", "bero": ""})
                logger.info("hns map: clear forwarded to match owner.")
            return

        raw = " ".join(args).strip()
        entry = Ghosts.resolve_map_entry(raw)
        if entry is None or not entry[0]:
            logger.info(f"hns map: '{raw}' isn't a builtin name (see "
                        f"/hns maps builtins) or a valid map:bero pair.")
            return
        map_id, bero = entry
        if st.is_conductor():
            st.game_state["next_map_override"] = [map_id, bero]
            br_disp = bero if bero else "(default spawn)"
            logger.info(f"hns map: next round will be {map_id}:{br_disp}.")
            self._publish_match_now()
        else:
            self._forward_match_command(kind="map_override",
                                         extra={"map_id": map_id, "bero": bero})
            br_disp = bero if bero else "(default spawn)"
            logger.info(f"hns map: forwarded {map_id}:{br_disp} to match owner.")

    def _hns_story(self, *args):
        """Bulk-write GSW + GSWF flags to fix the save-file story
        position before an HnS round-start teleport. Wraps
        apply_story_state().

        The preset (Ghosts.HNS_STORY_GSW_VALUES / HNS_STORY_GSWF_SET_BITS
        / HNS_STORY_GSWF_CLEAR_BITS) auto-applies on every client at
        the start of each match — the owner runs it inside
        _begin_match before publishing, and non-owners run it on the
        inactive->active transition in _publish_match_runtime_scratch.
        This /hns story command is for manual re-apply / inspection
        / ad-hoc tuning.

        Subcommands let you do ad-hoc fine-tuning:
          /hns story                              - apply the preset
          /hns story help                         - show this help
          /hns story gsw <i>=<v> [<i>=<v> ...]    - bulk GSW set
          /hns story set <bit> [<bit> ...]        - set GSWF bits to 1
          /hns story clear <bit> [<bit> ...]      - clear GSWF bits to 0
          /hns story show <bit|gsw=<i>>           - read current value

        Numbers may be decimal (1234) or hex (0x4D2). GSW indices are
        0..N where 0 is the 32-bit world word and 1+ are 8-bit per-event
        slots.
        """
        if not args:
            # Use the shared constants from Ghosts.py — same preset
            # _begin_match (round 1 owner) and _publish_match_runtime_scratch
            # (non-owners on inactive->active transition) auto-apply.
            preset_set_bits    = Ghosts.HNS_STORY_GSWF_SET_BITS
            preset_clear_bits  = Ghosts.HNS_STORY_GSWF_CLEAR_BITS
            preset_gsw_values  = Ghosts.HNS_STORY_GSW_VALUES
            range_lo = preset_set_bits[0] if preset_set_bits else 0
            range_hi = preset_set_bits[-1] if preset_set_bits else 0
            logger.info(f"hns story: applying preset — "
                        f"GSWF {range_lo}..{range_hi} set ({len(preset_set_bits)} bits), "
                        f"GSW {len(preset_gsw_values)} values")
            n_g, n_s, n_c, n_f = apply_story_state(
                gsw_values=preset_gsw_values,
                gswf_set_bits=preset_set_bits,
                gswf_clear_bits=preset_clear_bits,
                quiet=True,
            )
            logger.info(f"hns story: preset done — "
                        f"{n_g} GSW written, {n_s} GSWF set, {n_c} cleared"
                        + (f", {n_f} failed" if n_f else "") + ".")
            return

        if args[0].strip().lower() in ("help", "?", "-h", "--help"):
            logger.info("hns story: bulk-apply story flags. Auto-fires on")
            logger.info("every client at the start of each match (in")
            logger.info("_begin_match for the owner, on the inactive->active")
            logger.info("transition for non-owners). Manual subcommands:")
            logger.info("  /hns story                     - re-apply the preset")
            logger.info("                                   (Ghosts.HNS_STORY_*)")
            logger.info("  /hns story gsw <i>=<v> [...]   - bulk GSW set")
            logger.info("  /hns story set <bit> [...]     - set GSWF bits")
            logger.info("  /hns story clear <bit> [...]   - clear GSWF bits")
            logger.info("  /hns story show <bit|gsw=i>    - read one value")
            logger.info("Numbers may be decimal or hex (0x...).")
            return

        def _parse_int(tok: str):
            tok = tok.strip()
            try:
                return int(tok, 0)
            except ValueError:
                return None

        sub = args[0].strip().lower()
        rest = args[1:]

        if sub == "gsw":
            if not rest:
                logger.info("hns story gsw: usage: /hns story gsw <i>=<v> [...]")
                return
            pairs = {}
            for tok in rest:
                if "=" not in tok:
                    logger.info(f"hns story gsw: '{tok}' isn't <index>=<value>.")
                    return
                k, v = tok.split("=", 1)
                ki = _parse_int(k)
                vi = _parse_int(v)
                if ki is None or vi is None:
                    logger.info(f"hns story gsw: '{tok}' has a non-numeric "
                                f"index or value (use decimal or 0x hex).")
                    return
                pairs[ki] = vi
            n_g, _, _, n_f = apply_story_state(gsw_values=pairs)
            logger.info(f"hns story gsw: wrote {n_g} value(s)"
                        + (f", {n_f} failed" if n_f else "") + ".")
            return

        if sub in ("set", "clear"):
            if not rest:
                logger.info(f"hns story {sub}: usage: /hns story {sub} <bit> [<bit> ...]")
                return
            bits = []
            for tok in rest:
                bi = _parse_int(tok)
                if bi is None:
                    logger.info(f"hns story {sub}: '{tok}' isn't a number.")
                    return
                bits.append(bi)
            if sub == "set":
                _, n_s, _, n_f = apply_story_state(gswf_set_bits=bits)
                logger.info(f"hns story set: set {n_s} bit(s)"
                            + (f", {n_f} failed" if n_f else "") + ".")
            else:
                _, _, n_c, n_f = apply_story_state(gswf_clear_bits=bits)
                logger.info(f"hns story clear: cleared {n_c} bit(s)"
                            + (f", {n_f} failed" if n_f else "") + ".")
            return

        if sub == "show":
            if not rest:
                logger.info("hns story show: usage: /hns story show <bit|gsw=i>")
                return
            tok = rest[0].strip()
            if tok.lower().startswith("gsw="):
                ki = _parse_int(tok.split("=", 1)[1])
                if ki is None:
                    logger.info(f"hns story show: '{tok}' index not numeric.")
                    return
                try:
                    val = gsw_check(ki)
                    logger.info(f"hns story show: GSW[{ki}] = {val} (0x{val:X}).")
                except Exception as e:
                    logger.info(f"hns story show: read failed: {e}")
                return
            bi = _parse_int(tok)
            if bi is None:
                logger.info(f"hns story show: '{tok}' isn't a number.")
                return
            try:
                state = gswf_check(bi)
                logger.info(f"hns story show: GSWF[{bi}] = {1 if state else 0}.")
            except Exception as e:
                logger.info(f"hns story show: read failed: {e}")
            return

        logger.info(f"hns story: unknown subcommand '{sub}'. "
                    f"Use gsw / set / clear / show.")

    def _hns_hud(self, mode: str = "toggle"):
        ctx = self.ctx
        m = (mode or "toggle").strip().lower()
        cur = bool(getattr(ctx, "_match_hud_enabled", True))
        if m in ("on", "show", "1", "true"):
            new = True
        elif m in ("off", "hide", "0", "false"):
            new = False
        elif m in ("toggle", "t", ""):
            new = not cur
        else:
            logger.info(f"hns hud: unknown mode '{mode}'. Use on/off/toggle.")
            return
        ctx._match_hud_enabled = new
        logger.info(f"Match HUD {'ON' if new else 'OFF'}.")
        if not new:
            try:
                asyncio.create_task(_clear_match_hud(ctx))
            except Exception:
                pass
        else:
            self._publish_match_now()

    def _publish_match_now(self):
        """Schedule an immediate HUD + network publish so state changes
        appear without waiting for the periodic tick."""
        ctx = self.ctx
        try:
            asyncio.create_task(_publish_match_hud(ctx))
        except Exception:
            pass
        try:
            asyncio.create_task(_publish_match_to_network(ctx))
        except Exception:
            pass

    def _forward_match_command(self, *, kind: str, extra: dict | None = None):
        """Send a match-mutation Bounce to the match owner. Used when
        the local client isn't the owner — the owner receives the
        Bounce in _on_match_bounce and applies the mutation +
        republishes. The user never sees a "you're not the conductor"
        rejection; from their perspective every command works.
        """
        ctx = self.ctx
        st = getattr(ctx, "_match", None)
        if st is None or not st.conductor_slot:
            logger.info(f"hns: can't forward '{kind}' — no match owner.")
            return
        payload = {
            MATCH_BOUNCE_EVENT: True,
            "kind":   kind,
            "from":   int(getattr(ctx, "slot", 0) or 0),
        }
        if extra:
            payload.update(extra)
        try:
            asyncio.create_task(ctx.send_msgs([{
                "cmd":   "Bounce",
                "data":  payload,
                "slots": [int(st.conductor_slot)],
            }]))
        except Exception:
            logger.exception(f"hns: forward '{kind}' bounce failed")

    def _hns_role(self, *args):
        """Debug: manually set our published hide-and-seek role byte.
        Used to verify the v27 wire-format byte round-trips and that
        peers tint our name tag correctly (red for seeker, green for
        hider) before the full hide-and-seek game-mode driver lands.

        This override is silently superseded once we're an active
        member of a hide-and-seek lobby (the lobby's authoritative
        members_role assignment wins). Per-session; not persisted.

        Usage: /hns_role               - show current override
               /hns_role none          - clear override (publish role 0)
               /hns_role hider         - publish role 1 (green tag)
               /hns_role seeker        - publish role 2 (red tag)
        """
        ctx = self.ctx
        if not args:
            cur = getattr(ctx, "_hns_test_role", Ghosts.GAME_ROLE_NONE)
            label = Ghosts.GAME_ROLE_LABELS.get(cur, "?") or "none"
            logger.info(f"hns_role: current override = {label} ({cur}).")
            return
        raw = args[0].strip().lower()
        role = Ghosts.GAME_ROLE_NAMES.get(raw)
        if role is None:
            logger.info(f"hns_role: unknown role '{raw}'. Use none/hider/seeker.")
            return
        ctx._hns_test_role = role
        label = Ghosts.GAME_ROLE_LABELS.get(role, "") or "none"
        logger.info(f"hns_role: override set to {label}. Publishing.")
        try:
            asyncio.create_task(_publish_self_state(ctx))
        except Exception:
            pass


class TTYDContext(cmmCtx):
    command_processor = TTYDCommandProcessor
    game = "Paper Mario: The Thousand-Year Door"
    tags = {"AP"}
    dolphin_connected: bool = False
    seed_verified: bool = False
    slot_data: dict | None = {}
    checked_locations = set()
    previous_room = None
    death_sent: bool = False

    _ghost_subscribed: bool = False
    _ghost_peers: dict = {}

    _match: typing.Optional[Ghosts.MatchState] = None

    _match_subscribed: bool = False

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
            Utils.async_start(_subscribe_to_peers(self))
            if HNS_ENABLED:
                if self._match is None:
                    self._match = Ghosts.MatchState(
                        team=int(self.team or 0),
                        self_slot=int(self.slot or 0),
                    )
                Utils.async_start(_subscribe_to_match(self))
        elif cmd == "Retrieved":
            if "keys" not in args:
                logger.warning(f"invalid Retrieved packet to TTYDClient: {args}")
                return
            _on_ghost_update(self, args)
            if HNS_ENABLED:
                _dispatch_match_keys(self, args)
        elif cmd == "RoomInfo":
            self.seed_name = args["seed_name"]
        elif cmd == "SetReply":
            _on_ghost_update(self, args)
            if HNS_ENABLED:
                _dispatch_match_keys(self, args)
        elif cmd == "Bounced":

            data = args.get("data") or {}
            if data.get("ttyd_hit") is True:
                _on_inbound_hit(self, data)
            if HNS_ENABLED and data.get(MATCH_BOUNCE_EVENT) is True:
                _on_match_bounce(self, data)

    def on_deathlink(self, data: typing.Dict[str, typing.Any]) -> None:
        super().on_deathlink(data)
        trigger_death(self)

    async def disconnect(self, allow_autoreconnect: bool = False):
        st = getattr(self, "_match", None)
        if st is not None and st.is_conductor() and st.is_active():
            try:
                await _clear_match_from_network(self, st.team)
            except Exception:
                pass
        await super().disconnect()
        self.slot = None
        self.slot_data = None
        self.team = None
        self.checked_locations = set()
        self.seed_name = None
        self.seed_verified = False
        self._match = None
        self._match_subscribed = False
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
        if HNS_ENABLED:
            ctx.match_timer_task = asyncio.create_task(
                _match_timer_task(ctx), name="MatchTimer")

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
