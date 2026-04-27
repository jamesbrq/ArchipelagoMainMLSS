import asyncio
import math
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

RECEIVED_INDEX = 0x803DB860
RECEIVED_ITEM_ARRAY = 0x80001000
RECEIVED_LENGTH = 0x80000FFC
SEED = 0x80003210
GP_BASE = 0x803DAC18
GSWF_BASE = 0x178
GSW0 = 0x174
GSW_BASE = 0x578
ROOM = 0x803DF728
SHOP_POINTER = 0x8041EB60
SHOP_ITEM_OFFSET = 0x2F
SHOP_ITEM_PURCHASED = 0xD7

MARIO_PTR_ADDR = 0x8041E900
PLAYER_ANIM_NAME_OFFSET = 0x18   # const char* into game's static string pool
PLAYER_POSITION_OFFSET  = 0x8C   # vec3 (3 floats, big-endian)
PLAYER_ROTATION_Y_OFFSET = 0x1AC  # float
ANIM_NAME_READ_LEN = 32

# How far to the right of the player the ghost should appear, so it's
# actually visible rather than co-located inside our model.
GHOST_TEST_OFFSET_X = 50.0

# GameCube disc header Game ID - used to verify DME is hooked to the correct process
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

def gsw_set(index, value):
    dolphin.write_word(GP_BASE + GSW0, value) if index == 0 else dolphin.write_byte(GP_BASE + index + GSW_BASE, value)

def gsw_check(index):
    return dolphin.read_word(GP_BASE + GSW0) if index == 0 else dolphin.read_byte(GP_BASE + index + GSW_BASE)


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
    # The suffix is 1-3 trailing capital letters from {L, R, W}. Walk
    # backwards from the end stripping any of these letters.
    while name and name[-1] in "LRW":
        name = name[:-1]
    return name


def _read_self_state() -> dict | None:
    """Read the local Player struct in ONE IPC call and parse offsets
    locally. Doing this as 9 separate dolphin.read_bytes calls (the old
    way) caused visible jitter: the game advances frames between reads
    so the resulting state mixed values from different frames.

    The Player struct is contiguous; we read the first 0x1B0 bytes which
    covers all the offsets we need (largest is wPlayerDirectionCurrent at
    0x1AC). The struct read isn't truly atomic against the running game
    (Dolphin's read happens while the GameCube CPU is also writing) but
    it's near-instantaneous and dramatically tighter than 9 separate
    round-trips through asyncio + IPC."""
    try:
        player_ptr = int.from_bytes(
            dolphin.read_bytes(MARIO_PTR_ADDR, 4), "big"
        )
        if not (0x80000000 <= player_ptr < 0x81800000):
            return None

        # One big read covering everything we need.
        # Largest offset we read is mp+0x2D3 (jabara held-rest anim
        # playhead, signed byte). 0x2D4 = 724 bytes is still a single
        # IPC trip via Dolphin; the read isn't truly atomic against the
        # running game but it's near-instantaneous and dramatically
        # tighter than separate round-trips.
        buf = dolphin.read_bytes(player_ptr, 0x2D4)

        # Parse fields by offset directly from the buffer.
        # (No more multi-call tearing.)
        (flags2,) = struct.unpack_from(">I", buf, 0x4)
        (flags3,) = struct.unpack_from(">I", buf, 0xC)
        anim_ptr  = int.from_bytes(buf[0x18:0x1C], "big")
        # mp+0x1C is a pointer to a C string for the active paper anim.
        # NULL when paper mode is inactive. marioChgPaper sets this to
        # an anim name string, marioPaperOff clears it to 0.
        paper_anim_ptr = int.from_bytes(buf[0x1C:0x20], "big")
        (motion_timer,) = struct.unpack_from(">H", buf, 0x28)
        # motion_id at mp+0x2E identifies which mot_* function drives Mario's
        # state. Used by the mod to apply per-motion fixups (e.g. tube/roll
        # mode = 0x16 needs an extra 0.75 X scale). See marioMotTbl at
        # 0x80310030 for the full enum: 0x15=slit, 0x16=roll, 0x18=plane,
        # 0x19=ship, etc.
        (motion_id,) = struct.unpack_from(">H", buf, 0x2E)
        # Position is computed as:
        #   render_x = pos[0] + posOfs1[0] + posOfs2[0]
        #   render_y = pos[1] + posOfs1[1] + posOfs2[1]
        #   render_z = pos[2] + posOfs1[2] + posOfs2[2]
        # (matches marioDisp at 0x80056FB8-FF8: it sums mp+0x8C, mp+0x98,
        # and mp+0xA4 vectors before passing to PSMTXTrans).
        #
        # Without summing, mot_ship's bobble (encoded in posOfs1) and the
        # dock-to-water lerp (encoded in posOfs2) are lost on the ghost,
        # which appears stuck at its base position. Same applies to any
        # other motion that uses positional offsets (jumps, hits, etc).
        (base_x,  base_y,  base_z)  = struct.unpack_from(">fff", buf, 0x8C)
        (ofs1_x,  ofs1_y,  ofs1_z)  = struct.unpack_from(">fff", buf, 0x98)
        (ofs2_x,  ofs2_y,  ofs2_z)  = struct.unpack_from(">fff", buf, 0xA4)
        x = base_x + ofs1_x + ofs2_x
        y = base_y + ofs1_y + ofs2_y
        z = base_z + ofs1_z + ofs2_z
        (camera_angle,) = struct.unpack_from(">f", buf, 0x19C)
        (rot_y,) = struct.unpack_from(">f", buf, 0x1AC)
        # Pitch (mp+0xBC) and roll (mp+0xC4), in degrees. Used by:
        #   - plane mode (motionId 0x18): rotX nose-up/down, rotZ banks turn
        #   - tube/roll mode (motionId 0x16): both axes used for spinning
        # marioDisp branches on mp+0x2E to choose rotation order, but the
        # ghost just gets the same X/Y/Z values applied in the same order
        # so visual ends up matching.
        (rot_x,) = struct.unpack_from(">f", buf, 0xBC)
        (rot_z,) = struct.unpack_from(">f", buf, 0xC4)
        # Rotation pivot at mp+0xB0..0xBB (3 floats). marioDisp at
        # 0x80056DA0 translates by -(B0,B4,B8) BEFORE rotations and by
        # +(B0,B4,B8) AFTER, so rotations happen around this point and
        # not the model origin. In idle this is (0,0,0) and the
        # translates cancel out, but paper modes set it to wing-tip /
        # tube-center / etc. Without applying it, paper-mode rotations
        # spin the wrong axis or distort the model.
        (pivot_x, pivot_y, pivot_z) = struct.unpack_from(">fff", buf, 0xB0)
        # Per-axis scale at mp+0xC8..0xD3. marioDisp at 0x80056C0C reads
        # these and multiplies each by 2.0 (the base scale, or 1.2 in
        # mini-Mario mode flag) for the final scale. Idle: (1,1,1).
        # Paper modes: non-uniform - the tube/plane meshes have specific
        # aspect ratios that need scaling beyond the bounds of the original
        # Mario mesh. Without this the ghost is squished/stretched.
        (scale_x, scale_y, scale_z) = struct.unpack_from(">fff", buf, 0xC8)
        # stretchY: additional Y-axis scale from mp+0x130, gated by flags1
        # bit 0x01000000. marioDisp at 0x80056F8C tests this bit and only
        # then applies PSMTXScale(1, mp+0x130, 1) after rotations. We
        # pre-resolve here so the mod doesn't need to know about flags1:
        # publish either mp+0x130 (when flag set) or 1.0 (a no-op scale).
        # In normal play this is always 1.0; tube mode toggles the flag and
        # sets mp+0x130 to compress the model on Y.
        (flags1,) = struct.unpack_from(">I", buf, 0x0)
        if flags1 & 0x01000000:
            (stretch_y,) = struct.unpack_from(">f", buf, 0x130)
        else:
            stretch_y = 1.0

        # anim_name dereference - small extra read since the anim string
        # lives elsewhere in memory, but we only do one extra read instead
        # of doing it inline with all the others.
        anim_name = ""
        if 0x80000000 <= anim_ptr < 0x81800000:
            raw = dolphin.read_bytes(anim_ptr, 16)
            anim_name = raw.split(b"\x00", 1)[0].decode("ascii", errors="replace")

        # paper_anim dereference - same pattern. Empty string when
        # paper_anim_ptr is null/invalid -> mod treats this as "no paper
        # anim" and clears any active one via SetPaperAnimGroup.
        paper_anim = ""
        if 0x80000000 <= paper_anim_ptr < 0x81800000:
            raw = dolphin.read_bytes(paper_anim_ptr, 16)
            paper_anim = raw.split(b"\x00", 1)[0].decode("ascii", errors="replace")

        # paper_agb is the paper-pose AGB type (e.g. "a_kuru" for curl).
        # Python can't call animPoseGetGroupName on the GameCube's pose
        # objects, so the mod publishes it for us at a fixed address.
        # When local Mario isn't in paper mode, the mod writes an empty
        # string (zero bytes), which we read here as "".
        paper_agb = ""
        try:
            agb_raw = dolphin.read_bytes(
                Ghosts.SELF_PAPER_AGB_ADDR, Ghosts.SELF_PAPER_AGB_LEN)
            paper_agb = agb_raw.split(b"\x00", 1)[0].decode(
                "ascii", errors="replace")
        except Exception:
            # If the read fails (e.g. mod not loaded yet), treat as "no paper"
            pass
        # paper_local_time: a per-frame anim-playhead override for held
        # anims that don't progress on their own. Two known cases:
        #
        # 1. mot_hammer2 (motion 0x13) at line 80097B94 with paper anim
        #    "P_H_1A": animPoseSetLocalTime(activePoseId, mp+0x2C8 / 6.0).
        #    mp+0x2C8 is the accumulated spin charge.
        #
        # 2. mot_jabara (motion 0x14) at line 80097738 with regular anim
        #    "M_W_6" (held-shimmy on the pipe after the swing):
        #      animPoseSetLocalTime(activePoseId, (float)(int8_t)mp+0x2D3)
        #    mp+0x2D3 is a byte that increments 0..8 each frame then
        #    clamps - so the held animation freezes at frame 8.
        #    Without the override, the ghost keeps cycling M_W_6 instead
        #    of holding still like local Mario.
        #
        # Sentinel: -1.0 means "no override" (since both mp+0x2C8 and
        # mp+0x2D3 are non-negative). We publish 0.0 as a real override
        # in case the playhead should genuinely be 0.
        paper_local_time = -1.0
        if motion_id == 0x13 and paper_anim == "P_H_1A":
            (spin_charge,) = struct.unpack_from(">f", buf, 0x2C8)
            paper_local_time = spin_charge / 6.0
        elif motion_id == 0x14 and anim_name == "M_W_6":
            # mp+0x2D3 is a signed byte (int8_t).
            (mp_2d3,) = struct.unpack_from(">b", buf, 0x2D3)
            paper_local_time = float(mp_2d3)
    except Exception:
        return None

    map_name = read_string(ROOM, 16)
    if not map_name:
        return None

    return {
        "map": map_name,
        "anim": anim_name,
        "x": x,
        "y": y,
        "z": z,
        "rot_y": rot_y,
        "rot_x": rot_x,
        "rot_z": rot_z,
        "rot_pivot_x": pivot_x,
        "rot_pivot_y": pivot_y,
        "rot_pivot_z": pivot_z,
        "scale_x": scale_x,
        "scale_y": scale_y,
        "scale_z": scale_z,
        "stretch_y": stretch_y,
        "flags2": flags2,
        "flags3": flags3,
        "motion_timer": motion_timer,
        "motion_id": motion_id,
        "camera_angle": camera_angle,
        "paper_agb": paper_agb,
        "paper_anim": paper_anim,
        "paper_local_time": paper_local_time,
    }


def _write_peer_block(ctx) -> None:
    """Pack the current peer table into the binary block format and write
    it to Dolphin. Called from the sync loop each tick."""
    if ctx.team is None or ctx.slot is None:
        return
    peers = getattr(ctx, "_ghost_peers", {})
    try:
        payload = Ghosts.pack_peer_block(peers)
        dolphin.write_bytes(Ghosts.GHOSTS_ADDR, payload)
    except Exception as e:
        logger.warning(f"Failed to write ghost block to Dolphin: {e}")


async def _publish_self_state(ctx) -> None:
    """Read the local player's state from the game's Player struct and
    publish it to AP DataStorage. Skips silently if the read fails or the
    map name is empty (boot, cutscenes, between-map transitions)."""
    if ctx.team is None or ctx.slot is None:
        return
    state = _read_self_state()
    if state is None:
        return

    # Attach our display name so peers can render a name tag above our ghost.
    # ctx.player_names is keyed by slot id; if missing, fall back to a stub.
    own_name = ""
    try:
        own_name = ctx.player_names.get(ctx.slot, "") or ""
    except Exception:
        pass
    state["slot_name"] = own_name[:16]

    await ctx.send_msgs([{
        "cmd":         "Set",
        "key":         Ghosts.ghost_key(ctx.team, ctx.slot),
        "default":     None,
        "want_reply":  False,
        "operations":  [{"operation": "replace", "value": state}],
    }])


async def _subscribe_to_peers(ctx) -> None:
    if ctx.team is None or getattr(ctx, "_ghost_subscribed", False):
        return

    keys = []
    for slot_id, slot_info in (ctx.slot_info or {}).items():
        # Skip the synthetic Archipelago server slot (id 0), ourselves,
        # and any non-player slots (groups, spectators) which won't be
        # publishing ghost data.
        if slot_id == 0 or slot_id == ctx.slot:
            continue
        if slot_info.type != SlotType.player:
            continue
        keys.append(Ghosts.ghost_key(ctx.team, slot_id))

    if not keys:
        return

    await ctx.send_msgs([{"cmd": "SetNotify", "keys": keys}])
    await ctx.send_msgs([{"cmd": "Get",       "keys": keys}])
    ctx._ghost_subscribed = True


def _on_ghost_update(ctx, args: dict) -> None:
    """Handle SetReply (live broadcast) and Retrieved (response to our Get).
    Both deliver peer state in slightly different shapes; we normalize and
    dispatch each entry into Ghosts.ingest_peer_update."""
    if not hasattr(ctx, "_ghost_peers"):
        ctx._ghost_peers = {}

    if "keys" in args and isinstance(args["keys"], dict):
        # Retrieved: {"keys": {key: value, ...}}
        for key, value in args["keys"].items():
            Ghosts.ingest_peer_update(ctx._ghost_peers, key, value)
    elif "key" in args:
        # SetReply: {"key": ..., "value": ...}
        Ghosts.ingest_peer_update(ctx._ghost_peers, args["key"], args.get("value"))


def _on_ghost_disconnect(ctx) -> None:
    """Reset subscription state, clear known peers, and zero the magic in
    Dolphin so the mod stops rendering Ghosts immediately."""
    ctx._ghost_subscribed = False
    ctx._ghost_peers = {}
    try:
        dolphin.write_bytes(Ghosts.GHOSTS_ADDR, Ghosts.CLEAR_MAGIC)
    except Exception:
        pass


def _ghost_loopback_tick(ctx) -> None:
    if not getattr(ctx, "_ghost_loopback_active", False):
        return

    state = _read_self_state()
    if state is None:
        if not getattr(ctx, "_loopback_logged_none", False):
            logger.info("ghost_test: _read_self_state returned None")
            ctx._loopback_logged_none = True
        return
    ctx._loopback_logged_none = False

    if not getattr(ctx, "_loopback_logged_state", False):
        logger.info(f"ghost_test: state={state}")
        ctx._loopback_logged_state = True

    fake_peer_state = dict(state)
    fake_peer_state["x"] = state["x"] + GHOST_TEST_OFFSET_X
    fake_peer_state["slot_name"] = "GHOST"
    fake_peers = {Ghosts.ghost_key(0, 99): fake_peer_state}

    try:
        payload = Ghosts.pack_peer_block(fake_peers)
        dolphin.write_bytes(Ghosts.GHOSTS_ADDR, payload)
        if not getattr(ctx, "_loopback_logged_write", False):
            logger.info(f"ghost_test: wrote {len(payload)} bytes to 0x{Ghosts.GHOSTS_ADDR:08X}")
            ctx._loopback_logged_write = True
    except Exception as e:
        logger.warning(f"ghost_test write failed: {e}")


# Radius (in game units) of the ring of synthetic ghosts around the anchor.
# 100 is roughly 2-3 Mario widths, distinct enough to see all 8 separately.
GHOST_STRESS_RADIUS = 100.0


def _ghost_stress_tick(ctx) -> None:
    """Publish N synthetic peers in a ring around the local player. Each
    peer mirrors the local player's animation, rotation, and flag state -
    they all walk/idle/yawn in sync. Distinct palette colors (assigned
    by Ghosts.pack_peer_block based on slot index) let you tell them
    apart visually. The ring follows the player's current position each
    tick, so as you move all peers move with you.

    Count is read from ctx._ghost_stress_count (set when the test is
    toggled on). Defaults to 8 if missing for any reason."""
    if not getattr(ctx, "_ghost_stress_active", False):
        return

    count = getattr(ctx, "_ghost_stress_count", 8)

    state = _read_self_state()
    if state is None:
        return

    # Center the ring on the player's CURRENT position each tick. The
    # anchor captured at toggle-on time is no longer used as a position;
    # we keep it only to verify the test was enabled in a valid state.
    cx = state["x"]
    cy = state["y"]
    cz = state["z"]
    cmap = state["map"]

    # Larger rings need a bigger radius to not overlap. Scale roughly
    # with sqrt(count) so 32 ghosts fit nicely without overlapping.
    radius = GHOST_STRESS_RADIUS * math.sqrt(count / 8.0)

    fake_peers = {}
    for i in range(count):
        angle = (i / float(count)) * 2.0 * math.pi
        peer = dict(state)  # copy anim, rot_y, flags2, flags3, motion_timer
        peer["map"] = cmap
        peer["x"]   = cx + radius * math.cos(angle)
        peer["y"]   = cy
        peer["z"]   = cz + radius * math.sin(angle)
        # Synthetic name tag - lets us verify the name rendering works
        # without needing real multi-client setup. Each ghost gets a
        # distinct label so we can spot which slot is which.
        peer["slot_name"] = f"P{90 + i}"
        # Use ghost_key so pack_peer_block parses the slot index correctly.
        # We use slot ids 90..(90+count-1) to avoid collision with the
        # loopback test (slot 99) and with real player slots.
        fake_peers[Ghosts.ghost_key(0, 90 + i)] = peer

    try:
        payload = Ghosts.pack_peer_block(fake_peers)
        dolphin.write_bytes(Ghosts.GHOSTS_ADDR, payload)
        if not getattr(ctx, "_stress_logged_write", False):
            logger.info(f"ghost_stress: wrote {len(payload)} bytes "
                        f"({len(fake_peers)} peers) to "
                        f"0x{Ghosts.GHOSTS_ADDR:08X}")
            ctx._stress_logged_write = True
    except Exception as e:
        logger.warning(f"ghost_stress write failed: {e}")


class TTYDCommandProcessor(ClientCommandProcessor):
    def __init__(self, ctx: cmmCtx):
        super().__init__(ctx)

    def _cmd_set_gswf(self, bit_number: int):
        """Used to manually set a GSWF bit."""
        byte_address, bit = gswf_set(int(bit_number))
        logger.info(f"Bit {bit} written at {byte_address}")

    def _cmd_check_gswf(self, bit_number: int):
        """Used to manually check a GSWF bit."""
        result = gswf_check(int(bit_number))
        logger.info(f"GSWF Check: 0x{format(result, 'x')}")

    def _cmd_set_gsw(self, gsw: int, value: int):
        """Used to manually set a GSW flag."""
        gsw_set(int(gsw), int(value))

    def _cmd_check_gsw(self, gsw: int):
        """Used to manually check a GSW flag."""
        result = gsw_check(int(gsw))
        logger.info(f"GSWF Check: {result}")

    def _cmd_ghost_test(self):
        """Toggle the single-player ghost loopback test."""
        ctx = self.ctx
        ctx._ghost_loopback_active = not getattr(ctx, "_ghost_loopback_active", False)
        if ctx._ghost_loopback_active:
            logger.info("Ghost loopback test ON. A translucent ghost should "
                        "appear ~100 units to your right and trail your movement.")
        else:
            logger.info("Ghost loopback test OFF.")
            # Zero the magic so the mod stops rendering immediately.
            try:
                dolphin.write_bytes(Ghosts.GHOSTS_ADDR, Ghosts.CLEAR_MAGIC)
            except Exception:
                pass

    def _start_ghost_stress(self, count: int):
        """Shared toggle helper for /ghost_stress and /ghost_stress_32."""
        ctx = self.ctx

        # Toggling off if already running (regardless of count).
        if getattr(ctx, "_ghost_stress_active", False):
            ctx._ghost_stress_active = False
            ctx._ghost_stress_anchor = None
            ctx._ghost_stress_count = 0
            ctx._stress_logged_write = False
            logger.info("Ghost stress test OFF.")
            try:
                dolphin.write_bytes(Ghosts.GHOSTS_ADDR, Ghosts.CLEAR_MAGIC)
            except Exception:
                pass
            return

        # Clamp to mod's MAX_PEERS so we don't write garbage past the block.
        count = max(1, min(count, Ghosts.MAX_PEERS))

        # Toggling on - capture current position as the ring anchor
        state = _read_self_state()
        if state is None:
            logger.info("ghost_stress: cannot enable - _read_self_state returned None. "
                        "Are you in a map?")
            return
        ctx._ghost_stress_anchor = (state["x"], state["y"], state["z"], state["map"])
        ctx._ghost_stress_active = True
        ctx._ghost_stress_count = count
        ctx._stress_logged_write = False
        logger.info(f"Ghost stress test ON. {count} ghosts in a ring around "
                    f"({state['x']:.1f}, {state['z']:.1f}) on map '{state['map']}'.")

    def _cmd_ghost_stress(self):
        """Toggle the 8-ghost stress test. Generates 8 synthetic peers in a
        ring around your current position, each mirroring your animation
        state with a distinct color. Use to validate the mod handles 8
        concurrent ghosts. Disable the loopback test (/ghost_test) first
        to avoid both writing to the same shared block."""
        self._start_ghost_stress(8)

    def _cmd_ghost_stress_32(self):
        """Toggle the 32-ghost stress test. Same as /ghost_stress but with
        32 synthetic peers - the mod's full kMaxPeers capacity. Ring radius
        is auto-scaled so the ghosts don't overlap. Re-running the command
        toggles OFF (regardless of which size was active)."""
        self._start_ghost_stress(32)


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
        elif cmd == "Retrieved":
            if "keys" not in args:
                logger.warning(f"invalid Retrieved packet to TTYDClient: {args}")
                return
            _on_ghost_update(self, args)
        elif cmd == "RoomInfo":
            self.seed_name = args["seed_name"]
        elif cmd == "SetReply":
            _on_ghost_update(self, args)

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
            return  # Garbage data, skip
        if current_length > 0:
            return
        index = dolphin.read_word(RECEIVED_INDEX)
        if index > len(self.items_received):
            return  # Garbage data, skip
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
            return  # Garbage data, skip
        if death_byte == 1:
            dolphin.write_byte(0x80003240, 0)
            if not self.death_sent:
                await self.send_death(self.player_names[self.slot] + " had no life shrooms.")
            self.death_sent = False

    def save_loaded(self) -> bool:
        value = dolphin.read_byte(0x80003228)
        if value > 1:
            return False  # Garbage data
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



async def ttyd_ghost_loopback_task(ctx: TTYDContext):
    """Dedicated fast loop for the loopback test only. Runs at ~60 Hz to
    match the game's frame rate so the ghost has no visible lag behind
    the player. No-op unless /ghost_test is on, so this has zero cost in
    normal play."""
    while not ctx.exit_event.is_set():
        if (dolphin.is_hooked() and ctx.dolphin_connected
                and getattr(ctx, "_ghost_loopback_active", False)):
            try:
                _ghost_loopback_tick(ctx)
            except Exception:
                logger.exception("ghost loopback tick error")
        await asyncio.sleep(1.0 / 60)


async def ttyd_ghost_stress_task(ctx: TTYDContext):
    """Dedicated fast loop for the 8-ghost stress test. Runs at ~60 Hz to
    match the game's frame rate so the synthetic ghosts have no visible
    lag behind the local player. No-op unless /ghost_stress is on, so
    this has zero cost in normal play."""
    while not ctx.exit_event.is_set():
        if (dolphin.is_hooked() and ctx.dolphin_connected
                and getattr(ctx, "_ghost_stress_active", False)):
            try:
                _ghost_stress_tick(ctx)
            except Exception:
                logger.exception("ghost stress tick error")
        await asyncio.sleep(1.0 / 60)


# How often to publish our own state to AP DataStorage (in seconds).
# Too fast = chatty network; too slow = ghosts visibly lag. AP can handle
# 30Hz for this kind of frequent update fine; 20Hz is a safe default.
GHOST_PUBLISH_INTERVAL_S = 1.0 / 20.0

# How often to repaint the peer block in Dolphin RAM (in seconds).
# Should match the game frame rate (60Hz) so peers move smoothly even
# between network updates.
GHOST_RENDER_INTERVAL_S = 1.0 / 60.0


async def ttyd_ghost_sync_task(ctx: TTYDContext):
    """Real-AP ghost sync. Two responsibilities:

    1. Publish our local player state to AP DataStorage at ~20Hz so other
       peers can render us as a ghost. Skipped if not connected, not in a
       slot, or local read fails (cutscene/loading/title).
    2. Repaint the peer block (received from AP via SetReply / Retrieved)
       into Dolphin RAM at ~60Hz so the mod can render peers smoothly.

    Both are no-ops if the loopback or stress tests are active - those
    write the block themselves and we'd otherwise overwrite each other.

    This task does NOT do any locations/items work; that's ttyd_sync_task's
    job. We split them because ghost sync runs much faster than the game
    state polling loop (60Hz vs 2Hz)."""
    last_publish = 0.0
    while not ctx.exit_event.is_set():
        await asyncio.sleep(GHOST_RENDER_INTERVAL_S)

        if not (dolphin.is_hooked() and ctx.dolphin_connected):
            continue
        if ctx.team is None or ctx.slot is None:
            continue
        # Loopback / stress tests own the block while active. Don't fight them.
        if getattr(ctx, "_ghost_loopback_active", False):
            continue
        if getattr(ctx, "_ghost_stress_active", False):
            continue

        # Render: write peer block every tick so peers track smoothly.
        try:
            _write_peer_block(ctx)
        except Exception:
            logger.exception("ghost render tick error")

        # Publish: throttled to GHOST_PUBLISH_INTERVAL_S.
        now = asyncio.get_event_loop().time()
        if now - last_publish >= GHOST_PUBLISH_INTERVAL_S:
            last_publish = now
            try:
                await _publish_self_state(ctx)
            except Exception:
                logger.exception("ghost publish error")


# Sends player items from server
# Checks for player status to see if they are in/loading a level
# Checks location status inside of levels
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

def trigger_death(ctx: TTYDContext):
    if ctx.slot is not None and dolphin.is_hooked() and ctx.dolphin_connected and validate_connection():
        ctx.death_sent = True
        dolphin.write_byte(0x8000323F, 1)


def launch(*args):
    async def main(args):
        if args.patch_file:
            await asyncio.create_task(_patch_and_run_game(args.patch_file))
        ctx = TTYDContext(args.connect, args.password)
        ctx.server_task = asyncio.create_task(server_loop(ctx), name="ServerLoop")
        if gui_enabled:
            if tracker_loaded:  # UT Connection
                ctx.run_generator()
            ctx.run_gui()
        ctx.run_cli()
        ctx.gl_sync_task = asyncio.create_task(ttyd_sync_task(ctx), name="TTYD Sync Task")
        ctx.ghost_sync_task = asyncio.create_task(
            ttyd_ghost_sync_task(ctx), name="GhostSync")
        ctx.ghost_loopback_task = asyncio.create_task(
            ttyd_ghost_loopback_task(ctx), name="GhostLoopback")
        ctx.ghost_stress_task = asyncio.create_task(
            ttyd_ghost_stress_task(ctx), name="GhostStress")

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
    