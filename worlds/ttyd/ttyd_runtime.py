"""Unified TTYD runtime: ghost peer pipeline (publish, render, hits,
spin tracking, SFX), hide-and-seek game-mode helpers (role resolver,
solo test bots), match network sync (conductor-authoritative DataStorage +
Bounce events), in-game HUD overlay publish, conductor-only timer task,
and the 60 Hz ghost-sync orchestrator.

TTYDClient.py owns AP wiring, the items/locations sync task, and all
user-facing /commands. Helpers in this module that need ROOM /
read_string from TTYDClient go through the lazy accessors below to
avoid a load-time import cycle.
"""

import asyncio
import collections
import struct
import typing

from CommonClient import logger
import dolphin_memory_engine as dolphin
from NetUtils import SlotType

from . import Ghosts


def _client_read_string(addr: int, length: int) -> str:
    """Lazy import of TTYDClient.read_string. Called from inside
    runtime functions that need to read a NUL-terminated string
    from Dolphin RAM (e.g. the current map name)."""
    from . import TTYDClient
    return TTYDClient.read_string(addr, length)


def _client_ROOM() -> int:
    """Lazy accessor for the ROOM register address constant."""
    from . import TTYDClient
    return TTYDClient.ROOM


def _resolve_self_game_role(ctx) -> int:
    """Pick the v27 game_role byte we publish for our own slot.

    Resolution priority:
      1. Active match: if ctx._match exists with status in {HIDE, SEEK}
         and our slot has an assigned role, use that.
      2. Manual /hns role override (ctx._hns_test_role) for round-trip
         testing.
      3. GAME_ROLE_NONE.
    """
    match = getattr(ctx, "_match", None)
    self_slot = int(getattr(ctx, "slot", 0) or 0)
    if (match is not None
            and match.status in (Ghosts.MATCH_STATUS_HIDE, Ghosts.MATCH_STATUS_SEEK)):
        roles = (match.game_state or {}).get("members_role") or {}
        role_str = roles.get(self_slot) or roles.get(str(self_slot))
        if isinstance(role_str, str):
            return Ghosts.GAME_ROLE_NAMES.get(role_str.lower(), Ghosts.GAME_ROLE_NONE)
        if isinstance(role_str, int):
            if role_str in (Ghosts.GAME_ROLE_NONE,
                             Ghosts.GAME_ROLE_HIDER,
                             Ghosts.GAME_ROLE_SEEKER):
                return role_str

    test = getattr(ctx, "_hns_test_role", None)
    if isinstance(test, int) and test in (Ghosts.GAME_ROLE_NONE,
                                          Ghosts.GAME_ROLE_HIDER,
                                          Ghosts.GAME_ROLE_SEEKER):
        return test
    return Ghosts.GAME_ROLE_NONE

SOLO_BOT_SLOT_BASE = 91

SOLO_BOT_MAX       = 5

SOLO_BOT_DEFAULT_N = 3

SOLO_BOT_OFFSETS = [
    (+60.0,   0.0),
    (-60.0,   0.0),
    (+40.0, +60.0),
    (-40.0, +60.0),
    (  0.0, +90.0),
]

def _solo_default_role(idx: int, n_bots: int) -> int:
    """Pick a starting game_role for bot[idx] when /hns_solo starts.
    Solo mode puts the human player in the seeker role, so all bots
    default to HIDER (the targets the user is testing against).
    Can still be overridden per-bot via /hns_solo role."""
    return Ghosts.GAME_ROLE_HIDER

def _solo_inject(ctx, self_state) -> None:
    """Write each solo bot into ctx._ghost_peers as a synthetic peer.
    Called from the 60Hz publish tick. Cheap (small number of dict
    inserts). No-op if solo mode is off.

    Bot peers pin to a fixed world position the first time they're
    injected (current player position + per-bot offset). After that
    they stay put — the player can walk around them, hit them, etc.,
    without the bots tagging along. Pinning also locks the map name,
    so the bots don't follow you across map transitions; if you want
    bots in a new map, /hns_solo stop and start again there.
    """
    bots = getattr(ctx, "_solo_bots", None) or []
    if not bots:
        # Make sure no stale bot peers linger from a previous session.
        for slot in range(SOLO_BOT_SLOT_BASE, SOLO_BOT_SLOT_BASE + SOLO_BOT_MAX):
            ctx._ghost_peers.pop(Ghosts.ghost_key(0, slot), None)
        return

    cur_x = float(self_state.get("x", 0.0) or 0.0)
    cur_y = float(self_state.get("y", 0.0) or 0.0)
    cur_z = float(self_state.get("z", 0.0) or 0.0)
    cur_map = self_state.get("map", "") or ""

    for bot in bots:
        slot = int(bot.get("slot", 0))
        if slot <= 0:
            continue
        ox, oz = bot.get("offset", (0.0, 0.0))

        if "pinned_x" not in bot:
            bot["pinned_x"]   = cur_x + float(ox)
            bot["pinned_y"]   = cur_y
            bot["pinned_z"]   = cur_z + float(oz)
            bot["pinned_map"] = cur_map

        peer = {
            "map":         bot["pinned_map"],
            "anim":        "M_S_1",
            "x":           bot["pinned_x"],
            "y":           bot["pinned_y"],
            "z":           bot["pinned_z"],
            "rot_y":       0.0,
            "flags2":      0,
            "flags3":      0,
            "motion_timer": 0,
            "show_name":   0,                 # always render bot tags
            "hammerable":  0,                 # bots are hittable
            "team_id":     Ghosts.TEAM_NONE,
            "spin_dir_hint_y": 0,
            "spin_dir_hint_x": 0,
            "spin_dir_hint_z": 0,
            "camera_angle":    0.0,
            "slot_name":   bot.get("name", f"Bot{slot}")[:16],
            "paper_agb":   "",
            "paper_anim":  "",
            "rot_x":       0.0,
            "rot_z":       0.0,
            "rot_pivot_x": 0.0,
            "rot_pivot_y": 0.0,
            "rot_pivot_z": 0.0,
            "scale_x":     1.0,
            "scale_y":     1.0,
            "scale_z":     1.0,
            "stretch_y":   1.0,
            "motion_id":   0,
            "paper_local_time": -1.0,
            "sfx_events":  [],
            "active_loops": [],
            "game_role":   int(bot.get("game_role", Ghosts.GAME_ROLE_NONE)),
        }
        Ghosts.stamp_peer(peer)
        ctx._ghost_peers[Ghosts.ghost_key(0, slot)] = peer

def _solo_clear_peers(ctx) -> None:
    """Remove every bot peer from ctx._ghost_peers. Called on
    /hns_solo stop (and on disconnect)."""
    for slot in range(SOLO_BOT_SLOT_BASE, SOLO_BOT_SLOT_BASE + SOLO_BOT_MAX):
        ctx._ghost_peers.pop(Ghosts.ghost_key(0, slot), None)

def _solo_build_match(ctx, n_bots: int) -> "Ghosts.MatchState":
    """Stand up a local-only match with us as conductor + N bots as
    members. Starts in HIDE phase so the user immediately sees the
    seeker freeze + role colors. The user is always assigned SEEKER
    and the bots are all HIDERS — solo is a test harness for being
    a seeker, not a hider, so making the human the seeker is the
    canonical scenario.

    Inherits settings from the existing ctx._match.settings (round
    count, hide_phase_seconds, round_time_limit_seconds, map_pool,
    seeker_count_threshold) so the user's prior /hns set / /hns
    maps add configuration carries directly into solo mode without
    re-entering everything."""
    own_slot = int(getattr(ctx, "slot", 0) or 0)
    own_team = int(getattr(ctx, "team", 0) or 0)
    own_name = ""
    try:
        own_name = (ctx.player_names.get(own_slot, "") or "")[:16]
    except Exception:
        pass
    if not own_name:
        own_name = "Host"

    cur = getattr(ctx, "_match", None)
    if cur is not None and cur.settings is not None:
        settings = cur.settings
    else:
        settings = Ghosts.default_match_settings()

    # User = seeker (red tag, frozen during HIDE). Bots = hiders.
    members = [Ghosts.MatchMember(slot=own_slot, name=own_name,
                                   role=Ghosts.MATCH_ROLE_SEEKER)]
    members_role = {own_slot: "seeker"}
    for i in range(n_bots):
        bot_slot = SOLO_BOT_SLOT_BASE + i
        members.append(Ghosts.MatchMember(
            slot=bot_slot,
            name=f"Bot{i+1}",
            role=Ghosts.MATCH_ROLE_HIDER,
        ))
        members_role[bot_slot] = "hider"

    cur_map, cur_bero = _pick_round_map_for_settings(settings)

    # Seed the map rotation history so round 2's /hns next pick
    # via _pick_round_map(state) won't re-pick the same map.
    # Mirrors the seeker rotation seeding below.
    seed_history = []
    if cur_map:
        seed_history = [Ghosts.encode_map_pool_entry(cur_map, cur_bero)]

    state = Ghosts.MatchState(
        team=own_team,
        status=Ghosts.MATCH_STATUS_HIDE,
        members=members,
        self_slot=own_slot,
        timer_seconds=settings.hide_phase_seconds,
        conductor_slot=own_slot,
        settings=settings,
        game_state={
            "round":                   1,
            "round_total":             settings.round_count,
            "current_map":             cur_map,
            "current_bero":            cur_bero,
            "map_seq":                 1,
            "members_role":            members_role,
            "tally":                   {},
            "initial_seekers_history": [own_slot],
            "maps_played_history":     seed_history,
            "found_order":             [],
        },
    )
    return state


MARIO_PTR_ADDR = 0x8041E900

SFX_RING_CAPACITY    = 32

SFX_EVENT_BYTES      = 4

HIT_KIND_HAMMER = 1

GHOST_TEST_OFFSET_X = 50.0

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

    map_name = _client_read_string(_client_ROOM(), 16)
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


def _publish_match_runtime_scratch(ctx, addrs, self_role: int) -> None:
    """v29: write per-tick scratch the mod uses for hide-phase freeze
    + round-start map teleport. Cheap (a few small Dolphin writes).

    selfFrozen is 1 when our role is seeker AND the match is in HIDE
    phase. Always written every tick (defaulting to 0 when no match
    or wrong phase) so a stale 1 can't persist after disconnect /
    match end.

    Teleport: we track the conductor-published `map_seq` against
    ctx._last_applied_map_seq. On change, we copy current_map +
    increment our local pendingTeleportSeq (mod's per-frame check
    fires seqSetSeq once per change). Cross-match: when a new
    match begins (status transitions from inactive to active) we
    reset _last_applied_map_seq to 0 so the new match's round-1
    map_seq=1 reliably trips the != check, regardless of what
    value the prior match left it at."""
    match = getattr(ctx, "_match", None)

    # --- selfFrozen byte (unconditional write; default 0) ---
    frozen = 0
    if (match is not None
            and match.status == Ghosts.MATCH_STATUS_HIDE
            and self_role == Ghosts.GAME_ROLE_SEEKER):
        frozen = 1
    try:
        dolphin.write_bytes(addrs["self_frozen"], bytes([frozen]))
    except Exception:
        pass

    # No match -> nothing else to do (teleport scratch is only
    # touched while a match is live).
    if match is None:
        return

    cur_active = bool(match.is_active())
    prev_active = bool(getattr(ctx, "_match_was_active", False))
    if cur_active and not prev_active:
        # Match just transitioned inactive -> active. Reset map-seq
        # tracking and apply the story-state preset on every client
        # so non-owners pin their save before the round-1 teleport
        # lands them on the picked map. The owner already applied
        # the preset inside _begin_match before publishing; this
        # path covers everyone else.
        ctx._last_applied_map_seq = 0
        try:
            from .TTYDClient import apply_story_state
            apply_story_state(
                gsw_values=Ghosts.HNS_STORY_GSW_VALUES,
                gswf_set_bits=Ghosts.HNS_STORY_GSWF_SET_BITS,
                gswf_clear_bits=Ghosts.HNS_STORY_GSWF_CLEAR_BITS,
                quiet=True,
            )
        except Exception:
            logger.exception("hns: client-side story-state apply failed")
    ctx._match_was_active = cur_active

    # --- pending teleport ---
    gs = match.game_state or {}
    pub_map_seq = int(gs.get("map_seq", 0))
    last_seq = int(getattr(ctx, "_last_applied_map_seq", 0))
    if pub_map_seq != last_seq and cur_active:
        cur_map = (gs.get("current_map") or "")[:15]
        cur_bero = (gs.get("current_bero") or "")[:15]   # optional, future-proof
        if cur_map:
            map_buf  = cur_map.encode("ascii", errors="replace").ljust(16, bytes([0]))
            bero_buf = cur_bero.encode("ascii", errors="replace").ljust(16, bytes([0]))
            try:
                dolphin.write_bytes(addrs["pending_teleport_map"],  map_buf)
                dolphin.write_bytes(addrs["pending_teleport_bero"], bero_buf)
                tele_seq = (int(getattr(ctx, "_local_teleport_seq", 0)) + 1) & 0xFF
                dolphin.write_bytes(addrs["pending_teleport_seq"], bytes([tele_seq]))
                ctx._local_teleport_seq = tele_seq
                ctx._last_applied_map_seq = pub_map_seq
            except Exception:
                logger.exception("failed to write pending teleport scratch")


PEER_PUBLISH_HEARTBEAT_S = 1.0

PEER_PUBLISH_EPS_POS  = 0.5
PEER_PUBLISH_EPS_ROT  = 1.0
PEER_PUBLISH_EPS_SCALE = 0.01


def _wrap_angle_delta(a: float, b: float) -> float:
    """Shortest-arc difference (a - b) wrapped to [-180, 180]. Avoids
    triggering the rot-eps gate on harmless 359 -> 1 wrap-arounds."""
    d = float(a) - float(b)
    while d >  180.0: d -= 360.0
    while d < -180.0: d += 360.0
    return d


def _peer_state_changed(prev: dict, cur: dict) -> bool:
    """True iff the published peer state has changed enough since the
    last publish to warrant another one. Excludes motion_timer because
    it ticks every frame even for idle animations — receivers run their
    own playhead via animPoseMain so small drift is invisible."""
    # Definitive equality: any change forces publish.
    for k in ("map", "anim", "motion_id", "paper_agb", "paper_anim",
              "show_name", "hammerable", "team_id", "game_role",
              "slot_name"):
        if prev.get(k) != cur.get(k):
            return True
    # Active-loops list — element-wise, since order is stable for our
    # source.
    if list(prev.get("active_loops") or []) != list(cur.get("active_loops") or []):
        return True
    # Position deltas (meters, world space).
    for k in ("x", "y", "z"):
        if abs(float(prev.get(k, 0.0)) - float(cur.get(k, 0.0))) > PEER_PUBLISH_EPS_POS:
            return True
    # Rotation deltas (degrees). Use shortest-arc wrap so 359 -> 1
    # registers as 2 degrees, not 358.
    for k in ("rot_y", "rot_x", "rot_z"):
        if abs(_wrap_angle_delta(cur.get(k, 0.0), prev.get(k, 0.0))) > PEER_PUBLISH_EPS_ROT:
            return True
    if abs(_wrap_angle_delta(cur.get("camera_angle", 0.0),
                              prev.get("camera_angle", 0.0))) > PEER_PUBLISH_EPS_ROT:
        return True
    # Pivot + scale + stretch.
    for k in ("rot_pivot_x", "rot_pivot_y", "rot_pivot_z"):
        if abs(float(prev.get(k, 0.0)) - float(cur.get(k, 0.0))) > PEER_PUBLISH_EPS_POS:
            return True
    for k in ("scale_x", "scale_y", "scale_z", "stretch_y"):
        if abs(float(prev.get(k, 1.0)) - float(cur.get(k, 1.0))) > PEER_PUBLISH_EPS_SCALE:
            return True
    return False


def _publish_ghost_state_scratch(ctx):
    """Write every per-tick byte the mod reads out of GhostState:
    team_id, friendly_fire, selfGameRole, selfFrozen, and the
    pendingTeleport* fields. ALWAYS runs (independent of whether we
    can read the local Player struct), because the match state
    machine — especially the round-start teleport — has to keep
    advancing even when we're mid-cutscene or between maps. If we
    gated this on _read_self_state success, a non-conductor who
    happened to be in a transition cutscene the moment the conductor
    advanced rounds would silently drop the new map_seq and never
    teleport.

    Returns (addrs, team_id, self_role) so the caller can reuse the
    resolved values when it builds the published peer-state dict.
    `addrs` is None when the GhostState pointer hasn't been published
    yet (mod hasn't booted) — in that case, no Dolphin writes happen
    but the resolved team_id / self_role are still useful for the
    peer publish path."""
    addrs = ctx._ghost_addrs if _resolve_ghost_addresses(ctx) else None

    team_id = int(getattr(ctx, "_ghost_team_id", Ghosts.TEAM_NONE)) & 0xFF
    friendly_fire = 1 if getattr(ctx, "_ghost_friendly_fire", False) else 0
    self_role = _resolve_self_game_role(ctx)

    if addrs is not None:
        try:
            dolphin.write_bytes(addrs["self_team_id"], bytes([team_id]))
            dolphin.write_bytes(addrs["self_friendly_fire"], bytes([friendly_fire]))
            dolphin.write_bytes(addrs["self_game_role"],
                                 bytes([int(self_role) & 0xFF]))
        except Exception:
            pass
        try:
            _publish_match_runtime_scratch(ctx, addrs, self_role)
        except Exception:
            logger.exception("match runtime scratch publish failed")

    return addrs, team_id, self_role


async def _publish_self_state(ctx) -> None:
    """Read the local player's state from the game's Player struct and
    publish it to AP DataStorage so other peers can render us. Skips
    the AP `Set` silently if the read fails or the map name is empty
    (boot, cutscenes, between-map transitions). The match-runtime
    scratch (teleport / freeze / role bytes) is written FIRST so it
    keeps advancing even when the AP publish is being skipped — the
    HnS state machine has to make progress through cutscenes and map
    transitions, otherwise a non-conductor mid-transition when the
    conductor advances rounds would silently miss the new map_seq.

    Publish-on-change gate (saves AP server traffic): if nothing
    meaningful has changed since the last publish AND we're inside the
    heartbeat window AND no SFX events / active-loop changes are
    pending, skip the network Set entirely. Standing-still players
    drop from 20 Hz to 1 Hz outbound. The mod-side scratch writes
    (selfGameRole, selfFrozen, teleport, team flags) still happen on
    every tick — those are local Dolphin writes, not AP traffic."""
    if ctx.team is None or ctx.slot is None:
        return

    addrs, team_id, self_role = _publish_ghost_state_scratch(ctx)

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
    if addrs is not None:
        try:
            grace_byte = dolphin.read_bytes(addrs["hit_grace"], 1)
            if grace_byte and grace_byte[0] != 0:
                optout_grace = 1
        except Exception:
            pass
    state["hammerable"] = 1 if (optout_manual or optout_grace) else 0

    state["team_id"] = team_id
    state["game_role"] = self_role

    sfx_events = await _drain_sfx_ring(ctx)
    if sfx_events:
        state["sfx_events"] = sfx_events

    state["active_loops"] = _read_self_active_loops(ctx)

    now = asyncio.get_event_loop().time()
    last_state = getattr(ctx, "_last_published_state", None)
    last_t     = float(getattr(ctx, "_last_published_time", 0.0))
    loopback   = bool(getattr(ctx, "_ghost_loopback_active", False))
    must_publish = (
        last_state is None
        or loopback                                   # loopback ghost needs every tick
        or bool(sfx_events)                            # don't drop SFX events
        or (now - last_t) >= PEER_PUBLISH_HEARTBEAT_S  # heartbeat
        or _peer_state_changed(last_state, state)
    )

    # Always run the local injectors so the loopback ghost / solo bots
    # render every tick locally, regardless of whether we publish to AP.
    if loopback:
        _loopback_inject(ctx, state)
    if getattr(ctx, "_solo_bots", None):
        _solo_inject(ctx, state)

    if not must_publish:
        return

    hint_y, hint_x, hint_z = _consume_spin_hints(ctx)
    state["spin_dir_hint_y"] = hint_y
    state["spin_dir_hint_x"] = hint_x
    state["spin_dir_hint_z"] = hint_z

    await ctx.send_msgs([{
        "cmd":         "Set",
        "key":         Ghosts.ghost_key(ctx.team, ctx.slot),
        "default":     None,
        "want_reply":  False,
        "operations":  [{"operation": "replace", "value": state}],
    }])
    # Snapshot for the next change-check.
    ctx._last_published_state = dict(state)
    ctx._last_published_time  = now

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
            ctx._ghost_peers.pop(Ghosts.ghost_key(0, 99), None)
            return

    # Offset the X position so the ghost stands next to us, not on top.
    fake = dict(delayed_state)
    fake["x"] = delayed_state["x"] + GHOST_TEST_OFFSET_X
    fake["slot_name"] = "GHOST"
    Ghosts.stamp_peer(fake)
    ctx._ghost_peers[Ghosts.ghost_key(0, 99)] = fake

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
    match = getattr(ctx, "_match", None)
    if (match is not None
            and match.status in (Ghosts.MATCH_STATUS_HIDE, Ghosts.MATCH_STATUS_SEEK)):
        roles = (match.game_state or {}).get("members_role") or {}
        my_role = roles.get(ctx.slot) or roles.get(str(ctx.slot))
        if my_role == "hider":
            # Still drain the scratch slot so we don't accumulate
            # stale events.
            try:
                outbound_addr = ctx._ghost_addrs["outbound_hit"]
                dolphin.write_word(outbound_addr, 0)
            except Exception:
                pass
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

    match = getattr(ctx, "_match", None)
    if (match is not None
            and match.status in (Ghosts.MATCH_STATUS_HIDE, Ghosts.MATCH_STATUS_SEEK)
            and match.conductor_slot > 0):
        try:
            await ctx.send_msgs([{
                "cmd":   "Bounce",
                "slots": [match.conductor_slot],
                "data":  {
                    MATCH_BOUNCE_EVENT: True,
                    "kind":      "hit",
                    "attacker":  ctx.slot,
                    "victim":    target_slot,
                },
            }])
        except Exception:
            logger.exception("failed to send match hit event Bounce")

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
        logger.debug("inbound hit dropped: ghost-state container not yet resolved")
        return

    try:
        dolphin.write_word(ctx._ghost_addrs["pending_hit"], (kind_code & 0xFF) << 24)
    except Exception:
        logger.exception("failed to write inbound hit to mod scratch")

GHOST_TEST_DELAY_S = 1.0

GHOST_PUBLISH_INTERVAL_S = 1.0 / 20.0

GHOST_RENDER_INTERVAL_S = 1.0 / 60.0

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


async def _publish_match_hud(ctx) -> None:
    """Serialize the local match state and write it to the mod's scratch
    RAM (the lobby_hud sub-region of the GhostState container). Mod's
    DrawLobbyHud reads this and renders the overlay each frame.

    Safe to call repeatedly. Cheap (single 1KB write per call). If the
    user has the HUD toggled off, we instead clear the magic so the
    mod stops rendering."""
    if not getattr(ctx, "dolphin_connected", False):
        return
    if not _resolve_ghost_addresses(ctx):
        return
    if not getattr(ctx, "_match_hud_enabled", True):

        await _clear_match_hud(ctx)
        return

    state = getattr(ctx, "_match", None)
    block = Ghosts.pack_match_block(state)
    try:
        dolphin.write_bytes(ctx._ghost_addrs["lobby_hud"], block)
    except Exception:
        pass

async def _clear_match_hud(ctx) -> None:
    """Write 4 zero bytes to the match HUD magic field. Mod sees the
    mismatch and skips rendering this frame. Cheaper than packing a
    full inactive block."""
    if not getattr(ctx, "dolphin_connected", False):
        return
    if not _resolve_ghost_addresses(ctx):
        return
    try:
        dolphin.write_bytes(ctx._ghost_addrs["lobby_hud"], Ghosts.MATCH_CLEAR_MAGIC)
    except Exception:
        pass

MATCH_BOUNCE_JOIN  = "ttyd_match_join"   # member -> host: please add me

MATCH_BOUNCE_LEAVE = "ttyd_match_leave"  # member -> host: I'm leaving

MATCH_BOUNCE_EVENT = "ttyd_match_event"  # bidirectional game-mode event

def _kick_hud_publish(ctx) -> None:
    """Schedule an immediate HUD publish so the in-game overlay
    reflects the new match state without waiting for the 20Hz tick.
    Safe from non-async contexts; exceptions are swallowed because
    the periodic publish will catch up on the next tick anyway."""
    try:
        asyncio.create_task(_publish_match_hud(ctx))
    except Exception:
        pass

def _dispatch_match_keys(ctx, args: dict) -> None:
    """Inspect a SetReply / Retrieved packet's keys; route any that
    look like match keys to _on_match_net_update. Non-lobby keys are
    ignored here (the ghost-peer dispatcher in _on_ghost_update has
    its own filter on KEY_PREFIX)."""
    if "keys" in args and isinstance(args["keys"], dict):
        for key, value in args["keys"].items():
            if isinstance(key, str) and key.startswith(Ghosts.MATCH_KEY_PREFIX):
                _on_match_net_update(ctx, key, value)
    elif "key" in args:
        key = args["key"]
        if isinstance(key, str) and key.startswith(Ghosts.MATCH_KEY_PREFIX):
            _on_match_net_update(ctx, key, args.get("value"))

async def _publish_match_to_network(ctx) -> None:
    """Conductor-only: write the current MatchState to AP DataStorage
    so team members receive it via SetReply. No-op when we are not the
    conductor of an active match. Uses `replace` so the value is the
    full canonical state every time (no diff/merge complexity)."""
    state = getattr(ctx, "_match", None)
    if state is None or not state.is_conductor():
        return
    if ctx.team is None or ctx.slot is None:
        return
    key = Ghosts.match_key(state.team)
    payload = Ghosts.match_state_to_net_dict(state)
    try:
        await ctx.send_msgs([{
            "cmd":         "Set",
            "key":         key,
            "default":     0,
            "want_reply":  False,
            "operations": [{"operation": "replace", "value": payload}],
        }])
    except Exception:
        logger.exception("match net publish failed")


async def _clear_match_from_network(ctx, team: int) -> None:
    """Conductor-only: write the cleared sentinel to our match key."""
    if ctx.team is None or ctx.slot is None:
        return
    key = Ghosts.match_key(team)
    try:
        await ctx.send_msgs([{
            "cmd":         "Set",
            "key":         key,
            "default":     0,
            "want_reply":  False,
            "operations": [{"operation": "replace",
                             "value":     Ghosts.MATCH_NET_CLEARED}],
        }])
    except Exception:
        logger.exception("match net clear failed")

async def _subscribe_to_match(ctx) -> None:
    """Subscribe to our team's match key. Called once at Connected."""
    if ctx.team is None or getattr(ctx, "_match_subscribed", False):
        return
    key = Ghosts.match_key(int(ctx.team))
    try:
        await ctx.send_msgs([{"cmd": "SetNotify", "keys": [key]}])
        await ctx.send_msgs([{"cmd": "Get",       "keys": [key]}])
    except Exception:
        logger.exception("match subscribe failed")
        return
    ctx._match_subscribed = True


def _on_match_net_update(ctx, key: str, value) -> None:
    """Handle a SetReply / Retrieved entry whose key is a match key.
    If the conductor (someone else) published an update, mirror the
    state into ctx._match. If WE are the conductor, ignore — we own
    our local copy."""
    parsed = Ghosts.parse_match_key(key)
    if parsed is None:
        return
    team = parsed

    if isinstance(value, dict) and value.get("cleared") is True:
        cur = getattr(ctx, "_match", None)
        if cur is not None and not cur.is_conductor() and cur.team == team:
            ctx._match = Ghosts.MatchState(
                team=team,
                self_slot=int(getattr(ctx, "slot", 0) or 0),
            )
            logger.info("Match ended.")
            _kick_hud_publish(ctx)
        return

    if not isinstance(value, dict):
        return

    self_slot = int(getattr(ctx, "slot", 0) or 0)
    state = Ghosts.match_state_from_net_dict(value, self_slot)
    if state is None:
        return
    state.team = team

    cur = getattr(ctx, "_match", None)
    if cur is not None and cur.is_conductor() and cur.status != Ghosts.MATCH_STATUS_IDLE:
        return
    ctx._match = state
    _kick_hud_publish(ctx)

def _on_match_bounce(ctx, data: dict) -> None:
    """Inbound Bounce dispatch for match events. Owner-only: clients
    that aren't the local match owner ignore. The owner applies each
    forwarded mutation to local state and republishes via the next
    tick's _publish_match_to_network.

    Supported kinds:
      "hit"          — peer-vs-peer hammer hit (existing)
      "next"         — forwarded /hns next from any non-owner
      "stop"         — forwarded /hns stop from any non-owner
      "map_override" — forwarded /hns map <name> from any non-owner
                       (or empty map_id to clear the override)
    """
    state = getattr(ctx, "_match", None)
    if state is None or not state.is_conductor():
        return
    if data.get(MATCH_BOUNCE_EVENT) is not True:
        return
    kind = data.get("kind", "")
    publish_changed = False

    if kind == "hit":
        attacker = int(data.get("attacker", 0) or 0)
        victim   = int(data.get("victim",   0) or 0)
        if attacker > 0 and victim > 0:
            _on_match_hit_event(ctx, state, attacker, victim)
        # _on_match_hit_event already calls _publish via timer task;
        # no immediate republish needed.

    elif kind == "next":
        if state.is_active():
            state.timer_seconds = 0
            try:
                _on_match_timer_zero(ctx, state)
                publish_changed = True
            except Exception:
                logger.exception("forwarded /hns next failed")

    elif kind == "stop":
        if state.is_active():
            state.status = Ghosts.MATCH_STATUS_IDLE
            state.timer_seconds = 0
            state.members = []
            state.game_state = {}
            # Keep state.conductor_slot — see /hns stop in TTYDClient.py.
            # Clearing it would gate the publish_changed publish below
            # (is_conductor() check in _publish_match_to_network), so
            # non-owner clients would never see the post-stop IDLE
            # state and their HUDs would stay frozen on the prior phase.
            publish_changed = True

    elif kind == "map_override":
        if state.status in (Ghosts.MATCH_STATUS_IDLE,
                            Ghosts.MATCH_STATUS_ROUND_OVER):
            map_id = str(data.get("map_id", "") or "")[:15]
            bero   = str(data.get("bero",   "") or "")[:15]
            if map_id:
                state.game_state["next_map_override"] = [map_id, bero]
            else:
                state.game_state.pop("next_map_override", None)
            publish_changed = True

    elif kind == "leave":
        slot = int(data.get("slot", 0) or 0)
        if slot > 0 and slot not in state.opted_out:
            state.opted_out.append(slot)
            publish_changed = True

    elif kind == "join":
        slot = int(data.get("slot", 0) or 0)
        if slot > 0 and slot in state.opted_out:
            state.opted_out.remove(slot)
            publish_changed = True

    if publish_changed:
        try:
            asyncio.create_task(_publish_match_to_network(ctx))
        except Exception:
            logger.exception("forwarded-bounce republish failed")
        _kick_hud_publish(ctx)


async def _match_timer_task(ctx) -> None:
    """1 Hz match driver. Conductor-only.

    Auto-advance phases:
      HIDE  -> SEEK         on hide_phase_seconds expiry
                            (manual mode if hide_phase_seconds == 0)
      SEEK  -> ROUND_OVER   on round_time_limit_seconds expiry
                            (manual mode if round_time_limit_seconds == 0;
                            also auto-advances on all-hiders-found,
                            handled by _on_match_hit_event, not here)

    Manual phases (conductor uses /hns next):
      ROUND_OVER -> next round HIDE   (or MATCH_END if last round)
      MATCH_END  -> IDLE              (or /hns stop)

    Tally accrues per second during SEEK as long as the round is still
    active. With a positive round_time_limit_seconds the timer caps
    each hider's per-round contribution naturally; in SEEK manual mode
    accrual continues until /hns next or all-hiders-found ends the
    round.
    """
    while not ctx.exit_event.is_set():
        await asyncio.sleep(1.0)

        state = getattr(ctx, "_match", None)
        if state is None or not state.is_conductor():
            continue
        if state.status == Ghosts.MATCH_STATUS_IDLE:
            continue

        seek_manual = (
            state.status == Ghosts.MATCH_STATUS_SEEK
            and int(state.settings.round_time_limit_seconds) <= 0
        )
        hide_manual = (
            state.status == Ghosts.MATCH_STATUS_HIDE
            and int(state.settings.hide_phase_seconds) <= 0
        )

        # Tally accrual during SEEK: every tick the round is still
        # active (timer > 0 OR manual mode, which sits at timer == 0).
        if (state.status == Ghosts.MATCH_STATUS_SEEK
                and (state.timer_seconds > 0 or seek_manual)):
            gs = state.game_state
            tally = gs.setdefault("tally", {})
            members_role = gs.get("members_role") or {}
            for slot, role in members_role.items():
                if role == "hider":
                    s_int = int(slot) if isinstance(slot, str) else slot
                    tally[s_int] = float(tally.get(s_int, 0.0)) + 1.0

        # Decrement timer.
        if state.timer_seconds > 0:
            state.timer_seconds = max(0, state.timer_seconds - 1)

        # Auto-advance for HIDE and SEEK only. ROUND_OVER and
        # MATCH_END are manual. Both HIDE and SEEK stay manual when
        # their respective phase-seconds setting is 0 — _begin_round /
        # _on_match_timer_zero leave timer_seconds at 0 in that mode
        # and conductor uses /hns next to advance.
        if (state.timer_seconds == 0
                and ((state.status == Ghosts.MATCH_STATUS_HIDE and not hide_manual)
                     or (state.status == Ghosts.MATCH_STATUS_SEEK and not seek_manual))):
            try:
                _on_match_timer_zero(ctx, state)
            except Exception:
                logger.exception("match timer-zero handler failed")

        try:
            await _publish_match_to_network(ctx)
        except Exception:
            logger.exception("match timer publish failed")
        _kick_hud_publish(ctx)


import random as _random


ROUND_OVER_SECONDS = 10


def _begin_match(ctx, state) -> None:
    """Called from /hns start. Snapshots the roster, picks initial
    seekers, picks the first map, transitions to HIDE phase."""
    state.team = int(getattr(ctx, "team", 0) or 0)
    state.conductor_slot = int(getattr(ctx, "slot", 0) or 0)
    state.self_slot = state.conductor_slot

    # Snapshot members from current ghost peers + ourselves.
    own_slot = state.conductor_slot
    own_name = ""
    try:
        own_name = (ctx.player_names.get(own_slot, "") or "")[:16]
    except Exception:
        pass
    if not own_name:
        own_name = f"slot{own_slot}"

    members = [Ghosts.MatchMember(slot=own_slot, name=own_name,
                                   role=Ghosts.MATCH_ROLE_NONE)]

    # Add every currently-known peer on this team (not opted out).
    for key, peer in (getattr(ctx, "_ghost_peers", {}) or {}).items():
        try:
            slot = int(key.rsplit("_", 1)[-1])
        except (ValueError, IndexError):
            continue
        if slot == own_slot:
            continue
        if slot in (state.opted_out or []):
            continue
        peer_name = (peer or {}).get("slot_name", "") or f"slot{slot}"
        members.append(Ghosts.MatchMember(slot=slot, name=peer_name,
                                           role=Ghosts.MATCH_ROLE_NONE))

    state.members = members

    # Initialize game-state. _begin_round populates current_map +
    # appends the picked entry to maps_played_history.
    state.game_state = {
        "round":                   1,
        "round_total":             state.settings.round_count,
        "current_map":             "",
        "members_role":            {},
        "tally":                   {},
        "initial_seekers_history": [],
        "maps_played_history":     [],
        "found_order":             [],
    }

    # Pin the save-file story state before round 1's teleport fires.
    # Each member runs this on their own client (since _begin_match
    # is the local-state mutator that the owner runs before they
    # publish, and non-owners run their own copy when they receive
    # the published state — see the matching call in _on_match_net_update
    # if cross-client consistency on the pin is required).
    # Late-imported to avoid a circular dep on TTYDClient at module
    # load time.
    try:
        from .TTYDClient import apply_story_state
        apply_story_state(
            gsw_values=Ghosts.HNS_STORY_GSW_VALUES,
            gswf_set_bits=Ghosts.HNS_STORY_GSWF_SET_BITS,
            gswf_clear_bits=Ghosts.HNS_STORY_GSWF_CLEAR_BITS,
            quiet=True,
        )
    except Exception:
        logger.exception("hns: round-1 story-state apply failed")

    _begin_round(ctx, state)


def _begin_round(ctx, state) -> None:
    """Pick a map, pick initial seekers, transition to HIDE.

    Map selection priority:
      1. game_state["next_map_override"]: if the conductor manually
         chose a map via /hns map <name>, use that and clear the
         override so it only applies to one round.
      2. Random pick from settings.map_pool.

    `map_seq` (in game_state) is monotonically incremented on every
    new map pick. Each client's _publish_self_state writes the current
    map + seq to GhostState scratch when it sees the seq change; the
    mod compares against its last-applied seq and triggers
    seqSetSeq(kMapChange, ...) on each transition. This is what
    teleports every member to the round's map at round start."""
    gs = state.game_state

    override = gs.pop("next_map_override", None)
    if (isinstance(override, (list, tuple)) and len(override) >= 2
            and override[0]):
        cur_map  = str(override[0])[:15]
        cur_bero = str(override[1])[:15]
    else:
        cur_map, cur_bero = _pick_round_map(state)

    gs["current_map"]  = cur_map
    gs["current_bero"] = cur_bero
    gs["map_seq"]      = int(gs.get("map_seq", 0)) + 1
    seekers = _pick_initial_seekers(state)
    members_role = {}
    for m in state.members:
        members_role[m.slot] = "seeker" if m.slot in seekers else "hider"
    gs["members_role"] = members_role
    gs["found_order"] = []
    state.status = Ghosts.MATCH_STATUS_HIDE
    # hide_phase_seconds == 0 is the "manual" sentinel — leave the
    # timer at 0 so _match_timer_task's auto-advance branch
    # (gated on timer_seconds > 0) doesn't fire. Conductor
    # advances HIDE -> SEEK via /hns next.
    hps = int(state.settings.hide_phase_seconds)
    state.timer_seconds = hps if hps > 0 else 0


def _pick_round_map_for_settings(settings):
    """Settings-only variant of _pick_round_map. Useful when we
    need to pick a round map BEFORE the MatchState exists — e.g.
    /hns_solo start, which assembles the state in one shot rather
    than calling _begin_round on a partially-built state."""
    pool = list(settings.map_pool or [])
    if not pool:
        return ("", "")
    entry = _random.choice(pool)
    if ":" in entry:
        m, b = entry.split(":", 1)
        return (m.strip()[:15], b.strip()[:15])
    return (entry.strip()[:15], "")


def _pick_round_map(state):
    """Return (map, bero) for the next round.

    Map pool entries can be either:
      - "<map_name>"            — e.g. "gor_01"; bero defaults to empty
        (engine uses default spawn — works for some maps, not all).
      - "<map_name>:<bero>"     — e.g. "gor_01:dokan_1" — explicit
        entrance name. Required for most gameplay maps.

    Rotation: tracks `maps_played_history` in game_state so the same
    map isn't picked twice until every entry in the pool has been
    used once. When the pool is exhausted (every map has been picked),
    history wipes and selection re-opens to the full pool. Mirrors
    the existing initial-seeker rotation in _pick_initial_seekers.

    Returns ("", "") when the pool is empty."""
    pool_full = list(state.settings.map_pool or [])
    if not pool_full:
        return ("", "")

    gs = state.game_state
    history = list(gs.get("maps_played_history") or [])
    pool = [entry for entry in pool_full if entry not in history]
    if not pool:
        # Every map already played — start a fresh cycle.
        history = []
        pool = list(pool_full)

    entry = _random.choice(pool)
    history.append(entry)
    gs["maps_played_history"] = history

    if ":" in entry:
        m, b = entry.split(":", 1)
        return (m.strip()[:15], b.strip()[:15])
    return (entry.strip()[:15], "")


def _pick_initial_seekers(state):
    """Return a list of slots to be initial seekers this round.
    Pool tracks 'started-as-seeker' separately; resets when exhausted."""
    gs = state.game_state
    history = list(gs.get("initial_seekers_history") or [])
    member_slots = [m.slot for m in state.members]
    pool = [s for s in member_slots if s not in history]
    n = Ghosts.compute_seeker_count(len(state.members),
                                     state.settings.seeker_count_threshold)
    if n <= 0:
        return []
    if len(pool) < n:
        history = []
        pool = list(member_slots)
    chosen = _random.sample(pool, min(n, len(pool)))
    history.extend(chosen)
    gs["initial_seekers_history"] = history
    return list(chosen)


def _on_match_timer_zero(ctx, state) -> None:
    """Phase transition driven by the 1 Hz timer."""
    if state.status == Ghosts.MATCH_STATUS_HIDE:
        # Hide phase ended -> enter SEEK
        state.status = Ghosts.MATCH_STATUS_SEEK
        state.timer_seconds = state.settings.round_time_limit_seconds
    elif state.status == Ghosts.MATCH_STATUS_SEEK:
        # Time limit reached - end round (uncaught hiders already
        # accrued tally tick-by-tick during SEEK).
        _end_round(ctx, state, reason="time_limit")
    elif state.status == Ghosts.MATCH_STATUS_ROUND_OVER:
        if state.game_state.get("round", 1) < state.settings.round_count:
            state.game_state["round"] = int(state.game_state.get("round", 1)) + 1
            _begin_round(ctx, state)
        else:
            _end_match(ctx, state)
    elif state.status == Ghosts.MATCH_STATUS_END:
        # Match-end hold expired - return to IDLE.
        state.status = Ghosts.MATCH_STATUS_IDLE
        state.members = []
        state.game_state = {}


def _on_match_hit_event(ctx, state, attacker_slot: int, victim_slot: int) -> None:
    """Conductor: a hit was reported. If the victim is a hider in the
    current SEEK phase, convert them to a seeker. If no hiders remain,
    end the round."""
    if state.status != Ghosts.MATCH_STATUS_SEEK:
        return
    gs = state.game_state
    members_role = gs.setdefault("members_role", {})
    role = members_role.get(victim_slot) or members_role.get(str(victim_slot))
    if role != "hider":
        return
    members_role[victim_slot] = "seeker"
    found = gs.setdefault("found_order", [])
    found.append(victim_slot)
    for m in state.members:
        if m.slot == victim_slot:
            m.role = Ghosts.MATCH_ROLE_SEEKER
            break

    # Solo mode: update the bot's stored game_role so the next
    # _solo_inject tick publishes peer.gameRole = SEEKER.
    for bot in (getattr(ctx, "_solo_bots", None) or []):
        if int(bot.get("slot", 0)) == victim_slot:
            bot["game_role"] = Ghosts.GAME_ROLE_SEEKER
            break

    hiders_left = sum(1 for r in members_role.values() if r == "hider")
    if hiders_left == 0:
        _end_round(ctx, state, reason="all_found")


def _end_round(ctx, state, reason: str) -> None:
    """Transition SEEK -> ROUND_OVER. Tally already accrued tick-by-tick.

    Manual inter-round: timer is cleared so the HUD doesn't show a
    misleading countdown. The conductor advances to the next round
    via /hns next."""
    state.status = Ghosts.MATCH_STATUS_ROUND_OVER
    state.timer_seconds = 0
    state.game_state["last_round_reason"] = reason


def _end_match(ctx, state) -> None:
    """Compute leaderboard, transition to END. Manual exit: conductor
    runs /hns stop or starts a new match. Timer cleared so the HUD
    doesn't suggest auto-cleanup."""
    tally = state.game_state.get("tally") or {}
    member_names = {m.slot: m.name for m in state.members}
    rows = [(int(slot), member_names.get(int(slot), f"slot{slot}"), float(secs))
            for slot, secs in tally.items()]
    rows.sort(key=lambda r: -r[2])
    state.game_state["leaderboard"] = [list(row) for row in rows]
    state.status = Ghosts.MATCH_STATUS_END
    state.timer_seconds = 0

    try:
        logger.info("=" * 32)
        logger.info("Match Complete - Final Ranking:")
        for i, (_, name, secs) in enumerate(rows, 1):
            logger.info(f"  {i}. {name}: {int(secs)}s hidden")
        logger.info("=" * 32)
    except Exception:
        pass


async def ttyd_ghost_sync_task(ctx):
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
                await _publish_match_hud(ctx)
            except Exception:
                logger.exception("match hud publish error")
