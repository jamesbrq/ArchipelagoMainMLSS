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

RECEIVED_INDEX = 0x803DB860
RECEIVED_ITEM_ARRAY = 0x80001000
RECEIVED_LENGTH = 0x80000FFC
SEED = 0x80003210
GP_BASE = 0x803DAC18
GSWF_BASE = 0x178
GSW0 = 0x174
GSW_BASE = 0x578
ROOM = 0x803DF728

MARIO_PTR_ADDR = 0x8041E900

# All ghost-peer scratch addresses are now resolved at runtime through
# the GhostState pointer published in APSettings.ghostStatePtr (see
# Ghosts.py). The cached dict lives at ctx._ghost_addrs and contains
# absolute addresses for: peer_block, pending_hit, hit_pose_name,
# hit_reach_scale, hit_peer_width, outbound_hit, hit_grace,
# self_team_id, self_friendly_fire, max_rendered_peers,
# self_paper_agb, sfx_ring, sfx_ring_head/tail/seq/events, lobby_hud.
# _resolve_ghost_addresses(ctx) populates the dict; all publish/read
# helpers below bail if it isn't resolved yet.
SFX_RING_CAPACITY    = 32
SFX_EVENT_BYTES      = 4

HIT_KIND_HAMMER = 1

GHOST_TEST_OFFSET_X = 50.0

GAME_ID_ADDRESS = 0x80000000
EXPECTED_GAME_ID = b"G8ME01"


def _resolve_ghost_addresses(ctx) -> bool:
    """Read APSettings.ghostStatePtr from RAM and populate
    ctx._ghost_addrs with computed absolute addresses for every
    ghost-peer scratch region. Cached for the session - the GhostState
    pointer is allocated once at game boot and never moves.

    Returns True on success (addresses now cached), False if the
    pointer hasn't been published yet (mod's Init() hasn't run, or
    the game hasn't booted to the relevant state). Callers should
    treat False as "skip this tick" - it'll succeed on a later tick."""
    if getattr(ctx, "_ghost_addrs", None) is not None:
        return True
    try:
        ptr = int.from_bytes(
            dolphin.read_bytes(Ghosts.APSETTINGS_GHOST_STATE_PTR, 4), "big"
        )
    except Exception:
        return False
    # Treat zero as "not yet published". The mod writes a non-zero
    # pointer in mod::ghosts::Init() at boot.
    if ptr == 0:
        return False
    try:
        ctx._ghost_addrs = Ghosts.compute_ghost_state_addresses(ptr)
    except ValueError as e:
        # Pointer out of plausible range; usually means the game just
        # hasn't booted far enough yet. Try again next tick.
        logger.debug(f"ghost-state pointer not yet valid: {e}")
        return False
    logger.info(
        f"ghost-state container located at 0x{ptr:08X}; "
        f"peer block at 0x{ctx._ghost_addrs['peer_block']:08X}"
    )
    return True

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

    while name and name[-1] in "LRW":
        name = name[:-1]
    return name

def _read_self_state(ctx) -> dict | None:
    """Read the local Player struct in ONE IPC call and parse offsets
    locally. Doing this as 9 separate dolphin.read_bytes calls (the old
    way) caused visible jitter: the game advances frames between reads
    so the resulting state mixed values from different frames.

    The Player struct is contiguous; we read the first 0x1B0 bytes which
    covers all the offsets we need (largest is wPlayerDirectionCurrent at
    0x1AC). The struct read isn't truly atomic against the running game
    (Dolphin's read happens while the GameCube CPU is also writing) but
    it's near-instantaneous and dramatically tighter than 9 separate
    round-trips through asyncio + IPC.

    Takes ctx so it can resolve the GhostState container address (for
    reading the self-paper-AGB scratch field). If addresses haven't
    been resolved yet, falls back to leaving paper_agb empty rather
    than failing the whole read."""
    try:
        player_ptr = int.from_bytes(
            dolphin.read_bytes(MARIO_PTR_ADDR, 4), "big"
        )
        if not (0x80000000 <= player_ptr < 0x81800000):
            return None

        buf = dolphin.read_bytes(player_ptr, 0x2D4)

        (flags2,) = struct.unpack_from(">I", buf, 0x4)
        (flags3,) = struct.unpack_from(">I", buf, 0xC)
        anim_ptr  = int.from_bytes(buf[0x18:0x1C], "big")

        paper_anim_ptr = int.from_bytes(buf[0x1C:0x20], "big")
        (motion_timer,) = struct.unpack_from(">H", buf, 0x28)

        (motion_id,) = struct.unpack_from(">H", buf, 0x2E)

        (base_x,  base_y,  base_z)  = struct.unpack_from(">fff", buf, 0x8C)
        (ofs1_x,  ofs1_y,  ofs1_z)  = struct.unpack_from(">fff", buf, 0x98)
        (ofs2_x,  ofs2_y,  ofs2_z)  = struct.unpack_from(">fff", buf, 0xA4)
        x = base_x + ofs1_x + ofs2_x
        y = base_y + ofs1_y + ofs2_y
        z = base_z + ofs1_z + ofs2_z
        (camera_angle,) = struct.unpack_from(">f", buf, 0x19C)
        (rot_y,) = struct.unpack_from(">f", buf, 0x1AC)

        (rot_x,) = struct.unpack_from(">f", buf, 0xBC)
        (rot_z,) = struct.unpack_from(">f", buf, 0xC4)

        (pivot_x, pivot_y, pivot_z) = struct.unpack_from(">fff", buf, 0xB0)

        (scale_x, scale_y, scale_z) = struct.unpack_from(">fff", buf, 0xC8)

        (flags1,) = struct.unpack_from(">I", buf, 0x0)
        if flags1 & 0x01000000:
            (stretch_y,) = struct.unpack_from(">f", buf, 0x130)
        else:
            stretch_y = 1.0

        anim_name = ""
        if 0x80000000 <= anim_ptr < 0x81800000:
            raw = dolphin.read_bytes(anim_ptr, 16)
            anim_name = raw.split(b"\x00", 1)[0].decode("ascii", errors="replace")

        paper_anim = ""
        if 0x80000000 <= paper_anim_ptr < 0x81800000:
            raw = dolphin.read_bytes(paper_anim_ptr, 16)
            paper_anim = raw.split(b"\x00", 1)[0].decode("ascii", errors="replace")

        paper_agb = ""
        try:
            addrs = getattr(ctx, "_ghost_addrs", None) if ctx else None
            agb_addr = addrs.get("self_paper_agb") if addrs else None
            if agb_addr is not None:
                agb_raw = dolphin.read_bytes(agb_addr, Ghosts.SELF_PAPER_AGB_LEN)
                paper_agb = agb_raw.split(b"\x00", 1)[0].decode(
                    "ascii", errors="replace")
        except Exception:

            pass

        paper_local_time = -1.0
        if motion_id == 0x13 and paper_anim == "P_H_1A":
            (spin_charge,) = struct.unpack_from(">f", buf, 0x2C8)
            paper_local_time = spin_charge / 6.0
        elif motion_id == 0x14 and anim_name == "M_W_6":

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
    if not _resolve_ghost_addresses(ctx):
        return
    peer_block_addr = ctx._ghost_addrs["peer_block"]
    peers = getattr(ctx, "_ghost_peers", {})
    try:
        payload = Ghosts.pack_peer_block(peers)
        dolphin.write_bytes(peer_block_addr, payload)
    except Exception as e:
        logger.warning(f"Failed to write ghost block to Dolphin: {e}")

async def _drain_sfx_ring(ctx) -> list:
    """Read the mod's SFX event ring and return up to SFX_EVENTS_PER_SLOT
    most-recent events as a list of {sfx_id, seq, flags} dicts. Advances
    the ring's tail to mark events as consumed.

    The ring is SPSC: mod pushes on every psndSFXOn[/3D] call (filtered),
    Python pops once per publish tick. Capacity is 16 events; if more
    than 4 fired since the last drain we keep only the most recent 4.

    Returns [] on read failure or empty ring.

    NOTE: dolphin_memory_engine's read/write_bytes are SYNCHRONOUS. Do
    NOT wrap them in asyncio.wait_for - it raises TypeError silently
    swallowed by bare except, leaving the ring undrained. (Was the bug
    that stalled SFX sync v22-v23.)"""
    if not _resolve_ghost_addresses(ctx):
        return []
    addrs = ctx._ghost_addrs
    head_addr   = addrs["sfx_ring_head"]
    tail_addr   = addrs["sfx_ring_tail"]
    events_addr = addrs["sfx_ring_events"]
    try:
        head_b = dolphin.read_bytes(head_addr, 1)
        tail_b = dolphin.read_bytes(tail_addr, 1)
    except Exception:
        return []
    if not head_b or not tail_b:
        return []

    head = head_b[0]
    tail = tail_b[0]
    if head == tail:
        return []

    available = (head - tail) & 0xFF
    if available > SFX_RING_CAPACITY:
        available = SFX_RING_CAPACITY

    events = []
    cur = tail
    for _ in range(available):
        try:
            raw = dolphin.read_bytes(
                events_addr + cur * SFX_EVENT_BYTES,
                SFX_EVENT_BYTES)
        except Exception:
            break
        if not raw or len(raw) < SFX_EVENT_BYTES:
            break
        sfx_id = (raw[0] << 8) | raw[1]
        seq    = raw[2]
        flags  = raw[3]
        events.append({"sfx_id": sfx_id, "seq": seq, "flags": flags})
        cur = (cur + 1) % SFX_RING_CAPACITY

    try:
        dolphin.write_bytes(tail_addr, bytes([head]))
    except Exception:
        pass

    if len(events) > Ghosts.SFX_EVENTS_PER_SLOT:
        events = events[-Ghosts.SFX_EVENTS_PER_SLOT:]
    return events

async def _publish_self_state(ctx) -> None:
    """Read the local player's state from the game's Player struct and
    publish it to AP DataStorage. Skips silently if the read fails or the
    map name is empty (boot, cutscenes, between-map transitions)."""
    if ctx.team is None or ctx.slot is None:
        return
    state = _read_self_state(ctx)
    if state is None:
        return

    own_name = ""
    try:
        own_name = ctx.player_names.get(ctx.slot, "") or ""
    except Exception:
        pass
    state["slot_name"] = own_name[:16]

    state["show_name"] = 1 if getattr(ctx, "_ghost_names_hidden", False) else 0

    optout_manual = 1 if getattr(ctx, "_ghost_hammer_optout", False) else 0
    optout_grace = 0
    addrs = ctx._ghost_addrs if _resolve_ghost_addresses(ctx) else None
    if addrs is not None:
        try:
            grace_byte = dolphin.read_bytes(addrs["hit_grace"], 1)
            if grace_byte and grace_byte[0] != 0:
                optout_grace = 1
        except Exception:
            pass
    state["hammerable"] = 1 if (optout_manual or optout_grace) else 0

    team_id = int(getattr(ctx, "_ghost_team_id", Ghosts.TEAM_NONE)) & 0xFF
    state["team_id"] = team_id

    friendly_fire = 1 if getattr(ctx, "_ghost_friendly_fire", False) else 0
    if addrs is not None:
        try:
            dolphin.write_bytes(addrs["self_team_id"], bytes([team_id]))
            dolphin.write_bytes(addrs["self_friendly_fire"], bytes([friendly_fire]))
        except Exception:
            pass

    sfx_events = await _drain_sfx_ring(ctx)
    if sfx_events:
        state["sfx_events"] = sfx_events

    # Drain the spin-direction hint accumulators built up since the
    # last publish. Each is -1/0/+1 indicating fast rotation in that
    # axis since last publish. Receivers use these to disambiguate
    # >180-deg-per-publish spins. Plain shortest-path lerp can't tell
    # +250 from -110 from sample alone; the source-side hint resolves
    # it because we tracked the unwrapped angle at 60Hz.
    hint_y, hint_x, hint_z = _consume_spin_hints(ctx)
    state["spin_dir_hint_y"] = hint_y
    state["spin_dir_hint_x"] = hint_x
    state["spin_dir_hint_z"] = hint_z

    # v26 state-sync: read the mod's selfActiveLoops scratch (the mod
    # writes the current channel-map sample each frame) and include
    # in the published state so receivers can diff and start/stop
    # loops accordingly.
    state["active_loops"] = _read_self_active_loops(ctx)

    if getattr(ctx, "_ghost_loopback_active", False):
        _loopback_inject(ctx, state)

    await ctx.send_msgs([{
        "cmd":         "Set",
        "key":         Ghosts.ghost_key(ctx.team, ctx.slot),
        "default":     None,
        "want_reply":  False,
        "operations":  [{"operation": "replace", "value": state}],
    }])


def _loopback_inject(ctx, state: dict) -> None:
    """Inject the just-published self state into ctx._ghost_peers as a
    synthetic peer for /ghost_test. The 60Hz _write_peer_block will
    then pack and write it alongside any real peers.

    With GHOST_TEST_DELAY_S == 0 (default), the current state is
    injected immediately. With a non-zero delay, states are pushed
    onto a deque and dequeued once they're older than the delay -
    useful for solo testing where you want to compare your live
    actions against the ghost playing back your past actions."""
    now = asyncio.get_event_loop().time()

    if GHOST_TEST_DELAY_S <= 0.0:
        delayed_state = state
    else:
        buf = getattr(ctx, "_loopback_delay_buf", None)
        if buf is None:
            buf = collections.deque()
            ctx._loopback_delay_buf = buf
        buf.append((now, dict(state)))
        cutoff = now - GHOST_TEST_DELAY_S
        delayed_state = None
        while buf and buf[0][0] <= cutoff:
            _, delayed_state = buf.popleft()
        if delayed_state is None:
            # Not enough history yet (still warming up the delay buffer);
            # remove any prior loopback ghost so we don't render a stale
            # one from before the toggle.
            ctx._ghost_peers.pop(Ghosts.ghost_key(0, 99), None)
            return

    # Offset the X position so the ghost stands next to us, not on top.
    fake = dict(delayed_state)
    fake["x"] = delayed_state["x"] + GHOST_TEST_OFFSET_X
    fake["slot_name"] = "GHOST"
    ctx._ghost_peers[Ghosts.ghost_key(0, 99)] = fake

async def _publish_lobby_hud(ctx) -> None:
    """Serialize the local lobby state and write it to the mod's scratch
    RAM (the lobby_hud sub-region of the GhostState container). Mod's
    DrawLobbyHud reads this and renders the overlay each frame.

    Safe to call repeatedly. Cheap (single 1KB write per call). If the
    user has the HUD toggled off, we instead clear the magic so the
    mod stops rendering."""
    if not getattr(ctx, "dolphin_connected", False):
        return
    if not _resolve_ghost_addresses(ctx):
        return
    if not getattr(ctx, "_lobby_hud_enabled", True):

        await _clear_lobby_hud(ctx)
        return

    state = getattr(ctx, "_lobby", None)
    block = Ghosts.pack_lobby_block(state)
    try:
        dolphin.write_bytes(ctx._ghost_addrs["lobby_hud"], block)
    except Exception:
        pass

async def _clear_lobby_hud(ctx) -> None:
    """Write 4 zero bytes to the lobby HUD magic field. Mod sees the
    mismatch and skips rendering this frame. Cheaper than packing a
    full inactive block."""
    if not getattr(ctx, "dolphin_connected", False):
        return
    if not _resolve_ghost_addresses(ctx):
        return
    try:
        dolphin.write_bytes(ctx._ghost_addrs["lobby_hud"], Ghosts.LOBBY_CLEAR_MAGIC)
    except Exception:
        pass

async def _subscribe_to_peers(ctx) -> None:
    if ctx.team is None or getattr(ctx, "_ghost_subscribed", False):
        return

    keys = []
    for slot_id, slot_info in (ctx.slot_info or {}).items():

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

        for key, value in args["keys"].items():
            Ghosts.ingest_peer_update(ctx._ghost_peers, key, value)
    elif "key" in args:

        Ghosts.ingest_peer_update(ctx._ghost_peers, args["key"], args.get("value"))

def _on_ghost_disconnect(ctx) -> None:
    """Reset subscription state, clear known peers, and zero the magic in
    Dolphin so the mod stops rendering Ghosts immediately. Tolerates
    the ghost-state container not being resolved (e.g. disconnect
    before AP fully connected) - a no-op write is harmless."""
    ctx._ghost_subscribed = False
    ctx._ghost_peers = {}
    addrs = getattr(ctx, "_ghost_addrs", None)
    if addrs is not None:
        try:
            dolphin.write_bytes(addrs["peer_block"], Ghosts.CLEAR_MAGIC)
        except Exception:
            pass

def _peer_index_to_ap_slot(ctx, peer_index: int) -> typing.Optional[int]:
    """Translate a 0..31 peer-block index back to its AP slot ID.

    The mod-side hit detector returns "I hit slot N" where N is the
    position of the peer in the 32-slot block. Ghosts.pack_peer_block
    sorts peers by key (ttyd_ghost_<team>_<slot>) before packing, so
    we replicate the same sort here and pick the entry at index N.

    Returns None if the index is out of range or the peer dict has
    fewer entries than the index, or if we can't parse the slot from
    the key. The caller should treat None as "drop the event."
    """
    peers = getattr(ctx, "_ghost_peers", None) or {}
    sorted_keys = sorted(peers.keys())
    if peer_index < 0 or peer_index >= len(sorted_keys):
        return None
    key = sorted_keys[peer_index]
    try:

        return int(key.rsplit("_", 1)[-1])
    except (ValueError, IndexError):
        return None

async def _drain_outbound_hits(ctx) -> None:
    """Poll the mod's outbound-hit scratch slot. If non-zero, decode the
    event, look up the AP slot ID for the targeted peer, send a Bounce
    packet, and clear the slot.

    Wire format (matches GhostPeers.h's PackOutboundHit):
      byte 0 = hit kind (HIT_KIND_HAMMER = 1)
      byte 1 = peer block index (0..31)
      byte 2-3 = reserved (0)

    Bounce packet shape:
      {
        "cmd": "Bounce",
        "slots": [<victim AP slot id>],
        "data": {
          "ttyd_hit": True,    # discriminator - distinguishes our
                               # bounces from DeathLink and other
                               # generic Bounce traffic
          "from": <our slot>,
          "kind": "hammer",
        }
      }

    The discriminator key is critical: Bounce is a free-form generic
    relay, so DeathLink bounces, other mods' bounces, and ours all
    arrive in the same on_package handler. We tag with "ttyd_hit" so
    the receiver can filter cheaply.

    No-ops if not connected to a slot, or if the lookup fails (we
    silently clear the scratch and move on - dropping rare events is
    better than blocking the loop).
    """
    if ctx.team is None or ctx.slot is None:
        return
    if not _resolve_ghost_addresses(ctx):
        return
    outbound_addr = ctx._ghost_addrs["outbound_hit"]
    try:
        word = dolphin.read_word(outbound_addr)
    except Exception:
        return
    if word == 0:
        return

    kind = (word >> 24) & 0xFF
    peer_index = (word >> 16) & 0xFF

    try:
        dolphin.write_word(outbound_addr, 0)
    except Exception:
        pass

    if kind != HIT_KIND_HAMMER:

        return

    target_slot = _peer_index_to_ap_slot(ctx, peer_index)
    if target_slot is None:

        logger.debug(
            f"hit peer index {peer_index} doesn't resolve to an AP slot; "
            f"playing local stagger as a single-client loopback"
        )
        _on_inbound_hit(ctx, {"ttyd_hit": True, "kind": "hammer", "from": ctx.slot})
        return

    try:
        await ctx.send_msgs([{
            "cmd":   "Bounce",
            "slots": [target_slot],
            "data":  {
                "ttyd_hit": True,
                "from":     ctx.slot,
                "kind":     "hammer",
            },
        }])
    except Exception:
        logger.exception("failed to send hammer hit Bounce")

def _on_inbound_hit(ctx, data: dict) -> None:
    """Handle an inbound 'ttyd_hit' Bounce. Writes a kind code to the
    mod's PENDING_HIT scratch slot; the mod's per-frame consumer reads
    that on the next tick, plays the configured pose, and triggers the
    sound.

    Optional opt-out: if ctx._ghost_hammer_optout is set, ignore the
    incoming hit. (The /ghost_hammer command flips this flag; it
    lets a player turn off receiving stagger animations entirely.)
    Note that opt-out is only advisory - the attacker can still send
    Bounces; we just don't play the reaction.
    """
    if getattr(ctx, "_ghost_hammer_optout", False):
        return

    kind = data.get("kind")
    if kind == "hammer":
        kind_code = HIT_KIND_HAMMER
    else:
        return

    if not _resolve_ghost_addresses(ctx):
        # Mod's Init() hasn't run yet, or the game isn't booted enough
        # for the GhostState pointer to be valid. Drop this hit - it's
        # better to miss one stagger than to crash by writing to an
        # unresolved address.
        logger.debug("inbound hit dropped: ghost-state container not yet resolved")
        return

    try:
        dolphin.write_word(ctx._ghost_addrs["pending_hit"], (kind_code & 0xFF) << 24)
    except Exception:
        logger.exception("failed to write inbound hit to mod scratch")

GHOST_TEST_DELAY_S = 1.0



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

    def _cmd_ghost_names(self, mode: str = "toggle"):
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

    def _cmd_ghost_team(self, *args):
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
            self._cmd_ghost_team_status()
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
            self._cmd_ghost_team_status()

        elif sub in ("list", "ls"):
            self._cmd_ghost_team_list()

        else:
            logger.info(f"ghost_team: unknown subcommand '{sub}'. "
                        f"Use join/leave/status/list.")

    def _cmd_ghost_team_status(self):
        ctx = self.ctx
        team_id = int(getattr(ctx, "_ghost_team_id", Ghosts.TEAM_NONE))
        ff = bool(getattr(ctx, "_ghost_friendly_fire", False))
        label = Ghosts.TEAM_LABELS.get(team_id, "(unknown)")
        if team_id == Ghosts.TEAM_NONE:
            logger.info("Team: none. Friendly fire: "
                        f"{'ON' if ff else 'OFF'} (only matters with a team).")
        else:
            logger.info(f"Team: {label}. Friendly fire: {'ON' if ff else 'OFF'}.")

    def _cmd_ghost_team_list(self):
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

    def _cmd_ghost_friendly_fire(self, mode: str = "toggle"):
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

    def _cmd_lobby(self, *args):
        """Manage minigame lobbies. Step 1: local-only (no cross-player
        sync). The HUD shows your lobby state in the top-right corner
        once a lobby is active.

        Usage: /lobby create <name>      - create a new local lobby (you = host)
               /lobby leave              - exit current lobby
               /lobby status             - print lobby info to chat
               /lobby game <type>        - host: set game (hide_and_seek)
               /lobby start              - host: transition to playing
               /lobby stop               - host: transition back to waiting
               /lobby hud on/off/toggle  - toggle the in-game HUD overlay
        """
        ctx = self.ctx
        if not args:
            self._cmd_lobby_status()
            return

        sub = args[0].strip().lower()
        if sub == "create":
            self._cmd_lobby_create(*args[1:])
        elif sub == "leave":
            self._cmd_lobby_leave()
        elif sub in ("status", "info", "?"):
            self._cmd_lobby_status()
        elif sub == "game":
            self._cmd_lobby_game(*args[1:])
        elif sub == "start":
            self._cmd_lobby_start()
        elif sub == "stop":
            self._cmd_lobby_stop()
        elif sub == "hud":
            self._cmd_lobby_hud(*args[1:])
        else:
            logger.info(f"lobby: unknown subcommand '{sub}'. "
                        f"Use create/leave/status/game/start/stop/hud.")

    def _cmd_lobby_create(self, *name_parts):
        ctx = self.ctx
        if getattr(ctx, "_lobby", None) is not None:
            logger.info("lobby: you're already in a lobby. /lobby leave first.")
            return
        if not name_parts:
            logger.info("lobby: usage: /lobby create <name>")
            return
        name = " ".join(name_parts).strip()
        if not name:
            logger.info("lobby: name cannot be empty.")
            return

        own_name = ""
        try:
            own_name = (ctx.player_names.get(ctx.slot, "") or "")[:16]
        except Exception:
            pass
        if not own_name:
            own_name = "Host"
        slot = int(getattr(ctx, "slot", 0) or 0)

        ctx._lobby = Ghosts.LobbyState(
            lobby_id=f"local_{slot}",
            name=name[:16],
            game_type=Ghosts.GAME_TYPE_NONE,
            status=Ghosts.LOBBY_STATUS_WAITING,
            members=[Ghosts.LobbyMember(slot=slot, name=own_name,
                                        role=Ghosts.LOBBY_ROLE_HOST)],
            self_slot=slot,
        )
        logger.info(f"Created lobby '{name}' (you are host).")
        self._publish_lobby_now()

    def _cmd_lobby_leave(self):
        ctx = self.ctx
        if getattr(ctx, "_lobby", None) is None:
            logger.info("lobby: you're not in a lobby.")
            return
        ctx._lobby = None
        logger.info("Left the lobby.")
        self._publish_lobby_now()

    def _cmd_lobby_status(self):
        ctx = self.ctx
        st = getattr(ctx, "_lobby", None)
        if st is None:
            logger.info("Not in a lobby. /lobby create <name> to start one.")
            return
        game_label = Ghosts.GAME_TYPE_LABELS.get(st.game_type, "(none)") or "(none)"
        status_label = Ghosts.LOBBY_STATUS_LABELS.get(st.status, "?")
        logger.info(f"Lobby: {st.name}")
        logger.info(f"  Game: {game_label}")
        logger.info(f"  Status: {status_label}")
        if st.timer_seconds > 0:
            logger.info(f"  Timer: {st.timer_seconds}s")
        logger.info(f"  Members ({len(st.members)}):")
        for m in st.members:
            role_label = Ghosts.LOBBY_ROLE_LABELS.get(m.role, "")
            tag = f" [{role_label}]" if role_label else ""
            marker = "" if m.alive else " (out)"
            logger.info(f"    {m.name}{tag}{marker}")

    def _cmd_lobby_game(self, *args):
        ctx = self.ctx
        st = getattr(ctx, "_lobby", None)
        if st is None:
            logger.info("lobby: not in a lobby.")
            return
        if not st.is_host():
            logger.info("lobby: only the host can change game type.")
            return
        if not args:
            logger.info("lobby: usage: /lobby game <type>. "
                        "Available: hide_and_seek")
            return
        gtype = args[0].strip().lower()
        gid = Ghosts.GAME_TYPE_NAMES.get(gtype)
        if gid is None:
            logger.info(f"lobby: unknown game type '{gtype}'. "
                        f"Available: hide_and_seek")
            return
        st.game_type = gid
        label = Ghosts.GAME_TYPE_LABELS.get(gid, "")
        logger.info(f"Lobby game type set to {label}.")
        self._publish_lobby_now()

    def _cmd_lobby_start(self):
        ctx = self.ctx
        st = getattr(ctx, "_lobby", None)
        if st is None:
            logger.info("lobby: not in a lobby.")
            return
        if not st.is_host():
            logger.info("lobby: only the host can start the game.")
            return
        if st.game_type == Ghosts.GAME_TYPE_NONE:
            logger.info("lobby: set a game type first (/lobby game <type>).")
            return
        if st.status == Ghosts.LOBBY_STATUS_PLAYING:
            logger.info("lobby: already playing.")
            return
        st.status = Ghosts.LOBBY_STATUS_PLAYING
        logger.info("Lobby started.")
        self._publish_lobby_now()

    def _cmd_lobby_stop(self):
        ctx = self.ctx
        st = getattr(ctx, "_lobby", None)
        if st is None:
            logger.info("lobby: not in a lobby.")
            return
        if not st.is_host():
            logger.info("lobby: only the host can stop the game.")
            return
        st.status = Ghosts.LOBBY_STATUS_WAITING
        logger.info("Lobby stopped.")
        self._publish_lobby_now()

    def _cmd_lobby_hud(self, mode: str = "toggle"):
        """Toggle the in-game lobby HUD overlay."""
        ctx = self.ctx
        m = (mode or "toggle").strip().lower()
        cur = bool(getattr(ctx, "_lobby_hud_enabled", True))
        if m in ("on", "show", "1", "true"):
            new = True
        elif m in ("off", "hide", "0", "false"):
            new = False
        elif m in ("toggle", "t", ""):
            new = not cur
        else:
            logger.info(f"lobby_hud: unknown mode '{mode}'. Use on/off/toggle.")
            return
        ctx._lobby_hud_enabled = new
        logger.info(f"Lobby HUD {'ON' if new else 'OFF'}.")

        if not new:
            try:
                asyncio.create_task(_clear_lobby_hud(ctx))
            except Exception:
                pass
        else:
            self._publish_lobby_now()

    def _publish_lobby_now(self):
        """Helper: kick off an immediate publish of the current lobby
        state to the mod's scratch RAM. Don't wait for the periodic
        tick - we want the HUD to update instantly when commands fire."""
        try:
            asyncio.create_task(_publish_lobby_hud(self.ctx))
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

    # Cache of resolved absolute addresses for the GhostState container's
    # sub-regions. Populated by _resolve_ghost_addresses() once on first
    # successful read of APSettings.ghostStatePtr; persists for the
    # session. None until resolved; consumers must call the resolver
    # (or check getattr) before dereferencing.
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
        elif cmd == "Retrieved":
            if "keys" not in args:
                logger.warning(f"invalid Retrieved packet to TTYDClient: {args}")
                return
            _on_ghost_update(self, args)
        elif cmd == "RoomInfo":
            self.seed_name = args["seed_name"]
        elif cmd == "SetReply":
            _on_ghost_update(self, args)
        elif cmd == "Bounced":

            data = args.get("data") or {}
            if data.get("ttyd_hit") is True:
                _on_inbound_hit(self, data)

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

GHOST_PUBLISH_INTERVAL_S = 1.0 / 20.0

GHOST_RENDER_INTERVAL_S = 1.0 / 60.0

# Spin-direction tracking thresholds (Python side, source-of-truth).
# Each frame we sample local Mario's three rotation angles, compute the
# wrapped delta from the previous frame, and accumulate. At publish time
# we compare the accumulated unwrapped delta against the last published
# unwrapped value; if abs(delta) over the publish interval exceeds the
# threshold below, we set the wire-format hint byte to the sign of that
# delta. Receiver uses the hint to force lerp direction during fast
# spins where shortest-path lerp would pick the wrong way.
#
# 90 degrees over a publish interval = ~5 rev/sec, the regime where
# shortest-path becomes unreliable. Below this, plain shortest-path
# lerp works fine and we leave the hint at 0 (= no hint).
SPIN_HINT_THRESHOLD_DEG_PER_PUBLISH = 90.0


def _wrap180(deg: float) -> float:
    """Clamp an angle delta to [-180, 180] using minimal-rotation wrap."""
    while deg > 180.0:
        deg -= 360.0
    while deg < -180.0:
        deg += 360.0
    return deg


def _sample_spin_for_hint(ctx) -> None:
    """Per-frame sampler for spin-direction hints. Reads local Mario's
    yaw/pitch/roll, computes wrapped deltas from the previous frame
    (which are unambiguous at 60Hz - even the fastest game rotations
    don't exceed 180 degrees in 16ms), and accumulates an UNWRAPPED
    angular displacement over each publish interval.

    State stored on ctx:
      _spin_last_y/x/z       last raw angle read (from engine, wrapped)
      _spin_unwrap_y/x/z     accumulated unwrapped displacement since
                             the previous publish reset
      _spin_init             True after the first sample so the first
                             delta isn't computed against zero

    Cheap: a single 12-byte read at offsets 0x1AC, 0xBC, 0xC4 of the
    Player struct. Uses the existing MARIO_PTR_ADDR to find Mario.

    Errors silently ignored - if Mario isn't loaded we just skip the
    sample and the unwrap accumulator stays where it is. The next
    valid sample picks up where we left off."""
    try:
        mario_addr = int.from_bytes(
            dolphin.read_bytes(MARIO_PTR_ADDR, 4), "big")
        if not (0x80000000 <= mario_addr < 0x81800000):
            return
        # Single 12-byte block covering 0xBC..0xC8 covers rot_x and rot_z.
        # rot_y at 0x1AC needs a second small read.
        chunk_xz = dolphin.read_bytes(mario_addr + 0xBC, 12)  # 0xBC..0xC8
        (rot_x,)  = struct.unpack_from(">f", chunk_xz, 0x00)
        (rot_z,)  = struct.unpack_from(">f", chunk_xz, 0x08)
        chunk_y  = dolphin.read_bytes(mario_addr + 0x1AC, 4)
        (rot_y,) = struct.unpack_from(">f", chunk_y, 0x00)
    except Exception:
        return

    if not getattr(ctx, "_spin_init", False):
        ctx._spin_last_y = rot_y
        ctx._spin_last_x = rot_x
        ctx._spin_last_z = rot_z
        ctx._spin_unwrap_y = 0.0
        ctx._spin_unwrap_x = 0.0
        ctx._spin_unwrap_z = 0.0
        ctx._spin_init = True
        return

    # Per-frame wrapped delta - unambiguous at 60Hz. Accumulate into
    # the unwrapped displacement, which gets reset at publish time.
    ctx._spin_unwrap_y += _wrap180(rot_y - ctx._spin_last_y)
    ctx._spin_unwrap_x += _wrap180(rot_x - ctx._spin_last_x)
    ctx._spin_unwrap_z += _wrap180(rot_z - ctx._spin_last_z)
    ctx._spin_last_y = rot_y
    ctx._spin_last_x = rot_x
    ctx._spin_last_z = rot_z


def _consume_spin_hints(ctx) -> tuple:
    """Called at publish time. Returns (hint_y, hint_x, hint_z) where
    each is -1, 0, or +1 based on whether the unwrapped angular
    displacement since the last publish exceeded the threshold.
    Resets the unwrap accumulators."""
    if not getattr(ctx, "_spin_init", False):
        return (0, 0, 0)
    def sgn(d: float) -> int:
        if d >  SPIN_HINT_THRESHOLD_DEG_PER_PUBLISH: return  1
        if d < -SPIN_HINT_THRESHOLD_DEG_PER_PUBLISH: return -1
        return 0
    hy = sgn(ctx._spin_unwrap_y)
    hx = sgn(ctx._spin_unwrap_x)
    hz = sgn(ctx._spin_unwrap_z)
    ctx._spin_unwrap_y = 0.0
    ctx._spin_unwrap_x = 0.0
    ctx._spin_unwrap_z = 0.0
    return (hy, hx, hz)


def _read_self_active_loops(ctx) -> list:
    """v26: read the mod's selfActiveLoops scratch (mod-written every
    frame, sampled from g_localChannelMap). Returns a list of u16
    sfxIds currently playing on the local Mario. Receivers diff this
    against their tracked set to derive start/stop actions for loops.

    Returns [] on read failure or if the scratch isn't resolved yet."""
    addrs = getattr(ctx, "_ghost_addrs", None)
    if addrs is None:
        if not _resolve_ghost_addresses(ctx):
            return []
        addrs = ctx._ghost_addrs

    try:
        # Single 4-byte read for count + 3 pad, then 12-byte read for
        # the 6 uint16 entries. Could be one combined 16-byte read but
        # the count + entries layout may have padding so two reads is
        # safer.
        count_b = dolphin.read_bytes(addrs["self_active_loop_count"], 1)
        if not count_b:
            return []
        count = count_b[0]
        if count > Ghosts.ACTIVE_LOOPS_PER_PEER:
            count = Ghosts.ACTIVE_LOOPS_PER_PEER
        if count == 0:
            return []
        entries_b = dolphin.read_bytes(
            addrs["self_active_loops"],
            Ghosts.ACTIVE_LOOPS_PER_PEER * 2)
        if not entries_b or len(entries_b) < count * 2:
            return []
        loops = []
        for i in range(count):
            sid = (entries_b[i*2] << 8) | entries_b[i*2 + 1]
            if sid != 0:
                loops.append(sid)
        return loops
    except Exception:
        return []


async def ttyd_ghost_sync_task(ctx: TTYDContext):
    """Real-AP ghost sync. Two responsibilities:

    1. Publish our local player state to AP DataStorage at ~20Hz so other
       peers can render us as a ghost. Skipped if not connected, not in a
       slot, or local read fails (cutscene/loading/title). When the
       /ghost_test loopback toggle is on, the publish step also injects
       a synthetic peer copy into _ghost_peers via _loopback_inject().
    2. Repaint the peer block (received from AP via SetReply / Retrieved,
       and any synthetic loopback ghost) into Dolphin RAM at ~60Hz so the
       mod can render peers smoothly.

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

        try:
            await _drain_outbound_hits(ctx)
        except Exception:
            logger.exception("ghost outbound-hit drain error")

        # Sample local Mario's rotation each frame to maintain the
        # spin-direction hint accumulators. _publish_self_state will
        # consume them at 20Hz.
        _sample_spin_for_hint(ctx)

        try:
            _write_peer_block(ctx)
        except Exception:
            logger.exception("ghost render tick error")

        now = asyncio.get_event_loop().time()
        if now - last_publish >= GHOST_PUBLISH_INTERVAL_S:
            last_publish = now
            try:
                await _publish_self_state(ctx)
            except Exception:
                logger.exception("ghost publish error")

            try:
                await _publish_lobby_hud(ctx)
            except Exception:
                logger.exception("lobby hud publish error")

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
                    if goal == 1:
                        if not ctx.finished_game and gsw_check(1708) >= 18:
                            await ctx.send_msgs([{"cmd": "StatusUpdate", "status": ClientStatus.CLIENT_GOAL}])
                    elif goal == 2:
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
