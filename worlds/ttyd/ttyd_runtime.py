"""Unified TTYD runtime: ghost peer pipeline (publish, render, hits,
spin tracking, SFX).
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
        # mp+0x29 is the low byte of the u16 above. The engine writes
        # 0x18 to it at *both* Vivian sink-entry (via sth at 0x28-29)
        # and Vivian rise-entry (a separate write to just the low byte
        # by the un-Veil handler). Used by the kVivian paper-time pin
        # below as a phase-edge detector.
        (vivian_phase_byte,) = struct.unpack_from(">B", buf, 0x29)

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
        elif anim_name == "M_B_3" or paper_anim == "PM_B_1":
            # MarioMotion::kVivian (Veil) — Sink phase syncs correctly
            # with this branch; Rise phase still does NOT render right
            # on receivers. See PROJECT_STATE.md for full TODO notes.
            #
            # Current state: sink uses edge-pin to 24.0 (matches
            # N_marioForceVivianAnime's animPoseSetLocalTime call at
            # sink entry). Rise tries per-frame scrub to mp+0xA8
            # (wAnimPosition.y) — gets the *direction* right but the
            # paper anim still doesn't visually match what the
            # publisher shows. Several other approaches also failed:
            # see PROJECT_STATE.md "Vivian rise still wrong" TODO.
            #
            # Suspected real fix: the publisher's actual paper-anim
            # time scrub uses `vivianState[0x182]` (a half-word in
            # Vivian's *party state* struct, NOT Mario's player
            # struct). vivian_use:1801 calls
            #   animPoseSetLocalTime(paperPose, float(vivianState[0x182]))
            # each frame. We can't currently read that field from
            # Python because we don't have the Vivian state-struct
            # address — would need a mod-side scratch publish.
            prev_phase_byte = getattr(ctx, "_prev_vivian_phase_byte",
                                       0) if ctx is not None else 0
            if anim_name == "M_S_1" and int(vivian_phase_byte) != 0:
                # TODO(vivian-rise): see notes above. Current best
                # guess (mp+0xA8 / wAnimPosition.y); known not fully
                # correct. Left in place so the receiver gets *some*
                # decreasing value rather than nothing.
                paper_local_time = float(ofs2_y)
            elif int(vivian_phase_byte) != 0 and int(prev_phase_byte) == 0:
                # Sink-entry edge: pin once at 24.0, let engine tick.
                # This branch works correctly.
                paper_local_time = float(vivian_phase_byte)
            # else: held / sinking countdown with anim still M_B_3 —
            # leave at -1.0 so the engine ticks naturally.
    except Exception:
        return None

    # Snapshot mp+0x29 for the next call's edge-detect (covers both
    # Vivian sink-entry and rise-entry as a single rising-edge event).
    if ctx is not None:
        try:
            ctx._prev_vivian_phase_byte = int(vivian_phase_byte)
        except Exception:
            pass

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
        # flags1 reads as 0 during room transitions (the player struct
        # is in a torn-down state mid-kMapChange). Receivers gate on
        # this in pack_peer_block and write active=0 so the ghost
        # tears down for the duration of the transition instead of
        # snapping to (0,0,0) at world origin.
        "flags1": flags1,
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




PEER_PUBLISH_HEARTBEAT_S = 1.0

PEER_PRESENCE_TIMEOUT_S = 5.0  # peer counts as "in my room" only if heard within this

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
              "show_name", "hammerable", "team_id",
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
    """Write the per-tick bytes the mod reads out of GhostState:
    team_id and friendly_fire. ALWAYS runs (independent of whether we
    can read the local Player struct).

    Returns (addrs, team_id) so the caller can reuse the resolved
    values when it builds the published peer-state dict. `addrs` is
    None when the GhostState pointer hasn't been published yet (mod
    hasn't booted) — in that case no Dolphin writes happen but the
    resolved team_id is still useful for the peer publish path."""
    addrs = ctx._ghost_addrs if _resolve_ghost_addresses(ctx) else None

    team_id = int(getattr(ctx, "_ghost_team_id", Ghosts.TEAM_NONE)) & 0xFF
    friendly_fire = 1 if getattr(ctx, "_ghost_friendly_fire", False) else 0

    if addrs is not None:
        try:
            dolphin.write_bytes(addrs["self_team_id"], bytes([team_id]))
            dolphin.write_bytes(addrs["self_friendly_fire"], bytes([friendly_fire]))
        except Exception:
            pass

    return addrs, team_id


def _peer_sharing_my_room(ctx, my_map: str, now: float) -> bool:
    """True iff at least one other player is on my map and fresh within
    PEER_PRESENCE_TIMEOUT_S. Gates the high-rate stream; when False we
    publish only on discovery (connect + map change)."""
    if not my_map:
        return False
    peers = getattr(ctx, "_ghost_peers", None) or {}
    for peer in peers.values():
        if not isinstance(peer, dict):
            continue
        if (peer.get("map", "") or "") != my_map:
            continue
        last_seen = peer.get("_last_seen")
        if last_seen is None:
            continue
        try:
            if (now - float(last_seen)) <= PEER_PRESENCE_TIMEOUT_S:
                return True
        except (TypeError, ValueError):
            continue
    return False


async def _publish_self_state(ctx) -> None:
    """Read the local player's state from the game's Player struct and
    publish it to AP DataStorage so other peers can render us. Skips
    the AP `Set` silently if the read fails or the map name is empty
    (boot, cutscenes, between-map transitions).

    Publish-on-change gate (saves AP server traffic): if nothing
    meaningful has changed since the last publish AND we're inside the
    heartbeat window AND no SFX events / active-loop changes are
    pending, skip the network Set entirely. Standing-still co-located
    players drop from the 5 Hz ceiling to the 1 Hz heartbeat."""
    if ctx.team is None or ctx.slot is None:
        return

    addrs, team_id = _publish_ghost_state_scratch(ctx)

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

    sfx_events = await _drain_sfx_ring(ctx)
    if sfx_events:
        state["sfx_events"] = sfx_events

    state["active_loops"] = _read_self_active_loops(ctx)

    now = asyncio.get_event_loop().time()
    last_state = getattr(ctx, "_last_published_state", None)
    last_t     = float(getattr(ctx, "_last_published_time", 0.0))
    loopback   = bool(getattr(ctx, "_ghost_loopback_active", False))

    # Discovery (connect + map change) is exempt from the co-location
    # gate; it keeps peers' map view fresh and breaks the mutual-
    # suppression deadlock when two players enter the same room.
    is_discovery = (
        last_state is None
        or (last_state.get("map") != state.get("map"))
    )

    if is_discovery or loopback:
        must_publish = True
    elif _peer_sharing_my_room(ctx, state.get("map", ""), now):
        must_publish = (
            bool(sfx_events)                            # don't drop SFX events
            or (now - last_t) >= PEER_PUBLISH_HEARTBEAT_S  # heartbeat
            or _peer_state_changed(last_state, state)
        )
    else:
        # Alone: suppress all streaming. SFX ring already drained above
        # (can't overflow); with no one here, those events are dropped.
        must_publish = False

    # Run the loopback injector so the /ghost_test ghost renders every
    # tick locally, regardless of whether we publish to AP.
    if loopback:
        _loopback_inject(ctx, state)

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
    useful for single-client testing where you want to compare your
    live actions against the ghost playing back your past actions."""
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
        # Multi-pop merge: when several buffered states age past the
        # cutoff on the same tick (common after any small publish-loop
        # drift), we used to keep only the last popped state and drop
        # the rest, silently losing one-shot SFX events from the
        # intermediate frames. Loops survive that path because each
        # state carries a full active_loops snapshot — but discrete
        # events live in `sfx_events` and disappear if any state
        # carrying them gets skipped. Concatenate sfx_events from
        # every popped state so the loopback ghost faithfully replays
        # every Mario one-shot at the right offset position.
        merged_sfx: list = []
        while buf and buf[0][0] <= cutoff:
            _, delayed_state = buf.popleft()
            popped_sfx = delayed_state.get("sfx_events") if isinstance(delayed_state, dict) else None
            if popped_sfx:
                merged_sfx.extend(popped_sfx)
        if delayed_state is None:
            ctx._ghost_peers.pop(Ghosts.ghost_key(0, 99), None)
            return
        if merged_sfx:
            # Don't mutate the buffered dict — copy first so future
            # buffer reuse / debug-inspection sees the unmodified
            # original snapshot. Cap at SFX_EVENTS_PER_SLOT — the
            # binary peer slot can only carry that many per frame;
            # extras would be truncated at pack time anyway.
            delayed_state = dict(delayed_state)
            delayed_state["sfx_events"] = merged_sfx[:Ghosts.SFX_EVENTS_PER_SLOT]

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
        logger.debug("inbound hit dropped: ghost-state container not yet resolved")
        return

    try:
        dolphin.write_word(ctx._ghost_addrs["pending_hit"], (kind_code & 0xFF) << 24)
    except Exception:
        logger.exception("failed to write inbound hit to mod scratch")

GHOST_TEST_DELAY_S = 2.0

GHOST_PUBLISH_INTERVAL_S = 1.0 / 5.0

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




async def ttyd_ghost_sync_task(ctx):
    last_publish = 0.0
    while not ctx.exit_event.is_set():
        await asyncio.sleep(GHOST_RENDER_INTERVAL_S)

        if not (dolphin.is_hooked() and ctx.dolphin_connected):
            continue
        if ctx.team is None or ctx.slot is None:
            continue

        # Gate the entire pipeline on "save loaded into game world".
        # ctx.save_loaded() reads the AP scratch byte at 0x80003228
        # (1 = in-game). Without this, _write_peer_block runs against
        # a zeroed/garbage GhostState pointer at the title screen,
        # file-select, and intro cutscene, and we publish stale Mario
        # position / animation to other clients. Inbound _on_ghost_update
        # ingest keeps refreshing peers' _last_seen during menus, so
        # the heartbeat-timeout eviction in pack_peer_block won't
        # clobber legitimate teammates while we're parked here.
        try:
            in_game = ctx.save_loaded()
        except Exception:
            in_game = False
        if not in_game:
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