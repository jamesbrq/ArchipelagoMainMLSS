import struct
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from CommonClient import logger

GHOST_MAGIC  = 0x47484F53
VERSION      = 29

APSETTINGS_ADDR             = 0x80003220
APSETTINGS_GHOST_STATE_PTR  = APSETTINGS_ADDR + 0x3C  # mod::ghosts::GhostState *


# Peer block (SharedBlock): 16-byte header + 16 PeerSlots.
GS_OFF_PEER_BLOCK = 0x0000

MAX_PEERS    = 16
PEER_SIZE    = 212  # v26: +12 for activeLoops[6] uint16 + activeLoopCount byte + alignment
HEADER_SIZE  = 16
BLOCK_SIZE   = HEADER_SIZE + MAX_PEERS * PEER_SIZE   # 3408

# Hit/team scratch (compact section after peerBlock).
GS_OFF_PENDING_HIT          = GS_OFF_PEER_BLOCK + BLOCK_SIZE       # 0x0C90
GS_OFF_HIT_POSE_NAME        = GS_OFF_PENDING_HIT + 4               # 0x0C94
GS_OFF_HIT_REACH_SCALE      = GS_OFF_HIT_POSE_NAME + 16            # 0x0CA4
GS_OFF_HIT_PEER_WIDTH       = GS_OFF_HIT_REACH_SCALE + 4           # 0x0CA8
GS_OFF_OUTBOUND_HIT         = GS_OFF_HIT_PEER_WIDTH + 4            # 0x0CAC
GS_OFF_HIT_GRACE            = GS_OFF_OUTBOUND_HIT + 4              # 0x0CB0
GS_OFF_SELF_TEAM_ID         = GS_OFF_HIT_GRACE + 1                 # 0x0CB1
GS_OFF_SELF_FRIENDLY_FIRE   = GS_OFF_SELF_TEAM_ID + 1              # 0x0CB2
# +1 byte pad_team at 0x0CB3 to align the next uint32_t

GS_OFF_MAX_RENDERED_PEERS   = GS_OFF_SELF_FRIENDLY_FIRE + 2        # 0x0CB4

GS_OFF_SELF_PAPER_AGB_NAME  = GS_OFF_MAX_RENDERED_PEERS + 4        # 0x0CB8
SELF_PAPER_AGB_LEN          = 32

# SFX ring header + events.
GS_OFF_SFX_RING             = GS_OFF_SELF_PAPER_AGB_NAME + SELF_PAPER_AGB_LEN  # 0x0CD8
GS_OFF_SFX_RING_HEAD        = GS_OFF_SFX_RING + 0
GS_OFF_SFX_RING_TAIL        = GS_OFF_SFX_RING + 1
GS_OFF_SFX_RING_SEQ         = GS_OFF_SFX_RING + 2
GS_OFF_SFX_RING_EVENTS      = GS_OFF_SFX_RING + 4

SFX_RING_CAPACITY = 32

# Reserved block (raw 1024 bytes) — kept as padding so the GhostState
# layout is unchanged from v29.
GS_OFF_RESERVED_BLOCK = GS_OFF_SFX_RING_EVENTS + SFX_RING_CAPACITY * 4     # 0x0E1C
RESERVED_BLOCK_SIZE   = 1024

ACTIVE_LOOPS_PER_PEER = 6
GS_OFF_SELF_ACTIVE_LOOP_COUNT = GS_OFF_RESERVED_BLOCK + RESERVED_BLOCK_SIZE  # 0x121C
GS_OFF_SELF_ACTIVE_LOOPS      = GS_OFF_SELF_ACTIVE_LOOP_COUNT + 4         # 0x1220

# Reserved tail (0x122C..0x125B): bytes left in place so the layout
# matches v29 byte-for-byte. Nothing reads or writes them.
GS_OFF_RESERVED_TAIL = GS_OFF_SELF_ACTIVE_LOOPS + ACTIVE_LOOPS_PER_PEER * 2  # 0x122C
RESERVED_TAIL_SIZE   = 0x30                                                  # through 0x125B

GS_TOTAL_SIZE = GS_OFF_RESERVED_TAIL + RESERVED_TAIL_SIZE                # 0x125C


def compute_ghost_state_addresses(ghost_state_ptr: int) -> dict:
    """Given the GhostState base pointer (read from APSettings),
    return a dict mapping logical scratch-region names to absolute
    Dolphin RAM addresses. Used by TTYDClient to drive its writes.

    Validates the pointer looks plausible (in main RAM) and raises
    ValueError otherwise so callers can fail loudly rather than
    silently corrupting random memory.
    """
    if not (0x80000000 <= ghost_state_ptr < 0x81800000):
        raise ValueError(
            f"GhostState pointer 0x{ghost_state_ptr:08X} out of game RAM range; "
            f"the mod's Init() may not have run yet"
        )
    base = ghost_state_ptr
    return {
        "peer_block":         base + GS_OFF_PEER_BLOCK,
        "pending_hit":        base + GS_OFF_PENDING_HIT,
        "hit_pose_name":      base + GS_OFF_HIT_POSE_NAME,
        "hit_reach_scale":    base + GS_OFF_HIT_REACH_SCALE,
        "hit_peer_width":     base + GS_OFF_HIT_PEER_WIDTH,
        "outbound_hit":       base + GS_OFF_OUTBOUND_HIT,
        "hit_grace":          base + GS_OFF_HIT_GRACE,
        "self_team_id":       base + GS_OFF_SELF_TEAM_ID,
        "self_friendly_fire": base + GS_OFF_SELF_FRIENDLY_FIRE,
        "max_rendered_peers": base + GS_OFF_MAX_RENDERED_PEERS,
        "self_paper_agb":     base + GS_OFF_SELF_PAPER_AGB_NAME,
        "sfx_ring":           base + GS_OFF_SFX_RING,
        "sfx_ring_head":      base + GS_OFF_SFX_RING_HEAD,
        "sfx_ring_tail":      base + GS_OFF_SFX_RING_TAIL,
        "sfx_ring_seq":       base + GS_OFF_SFX_RING_SEQ,
        "sfx_ring_events":    base + GS_OFF_SFX_RING_EVENTS,
        "self_active_loop_count": base + GS_OFF_SELF_ACTIVE_LOOP_COUNT,
        "self_active_loops":      base + GS_OFF_SELF_ACTIVE_LOOPS,
    }

SFX_EVENTS_PER_SLOT = 4
SFX_FLAG_3D = 0x01
# Note: v25's SFX_FLAG_STOP removed. v26 uses state-sync (peer.activeLoops)
# instead of stop events for loop termination.

TEAM_NONE   = 0
TEAM_RED    = 1
TEAM_BLUE   = 2
TEAM_GREEN  = 3
TEAM_YELLOW = 4

TEAM_NAMES = {
    "none":   TEAM_NONE,
    "red":    TEAM_RED,
    "blue":   TEAM_BLUE,
    "green":  TEAM_GREEN,
    "yellow": TEAM_YELLOW,
}

TEAM_LABELS = {
    TEAM_NONE:   "",
    TEAM_RED:    "Red",
    TEAM_BLUE:   "Blue",
    TEAM_GREEN:  "Green",
    TEAM_YELLOW: "Yellow",
}

_PEER_FMT   = ">B 15s 16s ffff BBBB I I H B B B bbb f 16s 32s 16s ff fff fff f H 2x f B B B x HBBHBBHBBHBB HHHHHH"
_HEADER_FMT = ">IIII"

assert struct.calcsize(_PEER_FMT)   == PEER_SIZE,   f"peer fmt size {struct.calcsize(_PEER_FMT)} != {PEER_SIZE}"
assert struct.calcsize(_HEADER_FMT) == HEADER_SIZE, "header fmt size mismatch"

KEY_PREFIX = "ttyd_ghost_"

def ghost_key(team: int, slot: int) -> str:
    return f"{KEY_PREFIX}{team}_{slot}"

_PALETTE = [
    (255, 128, 128),
    (128, 255, 128),
    (128, 160, 255),
    (255, 255, 128),
    (255, 128, 255),
    (128, 255, 255),
    (255, 192, 128),
    (192, 128, 255),
]
_GHOST_ALPHA = 96

def color_for_slot(slot: int) -> tuple:
    r, g, b = _PALETTE[slot % len(_PALETTE)]
    return (r, g, b, _GHOST_ALPHA)

# Heartbeat-based presence: pack_peer_block drops any peer whose
# `_last_seen` (monotonic timestamp stamped on ingest / synth) is older
# than this threshold. Avoids rendering a stuck ghost at the last known
# position when the publishing client disconnects or stalls. Picked to
# survive a single dropped publish at the 1 Hz heartbeat rate without
# leaving a stuck ghost behind when a client goes idle.
PEER_PRESENCE_TIMEOUT_S = 4.0

def stamp_peer(peer: dict) -> None:
    """Mark `peer` as freshly observed. Called from ingest paths and
    from any local synthesizer that writes into ctx._ghost_peers
    (e.g. the /ghost_test loopback)."""
    if isinstance(peer, dict):
        peer["_last_seen"] = time.monotonic()

def ingest_peer_update(peers: dict, key: str, value) -> None:
    """Apply one server-side update to the caller's peer dict. Mutates in
    place. `value` is the raw value from the AP package - either a dict
    payload or None (peer cleared their state)."""
    if not key.startswith(KEY_PREFIX):
        return
    if value is None or not isinstance(value, dict):
        peers.pop(key, None)
        return
    stamp_peer(value)
    peers[key] = value

def pack_peer_block(peers: dict) -> bytes:
    """Pack peers (dict of key -> state-dict) into the binary peer block.

    Returns exactly BLOCK_SIZE bytes. Excess peers beyond MAX_PEERS
    are dropped; missing fields default to zero / empty string. Malformed
    individual peers are logged and skipped without breaking the rest of
    the block.

    Also prunes stale entries: any peer whose `_last_seen` is older
    than PEER_PRESENCE_TIMEOUT_S is skipped from the binary output AND
    evicted from `peers` so the dict doesn't grow unboundedly when a
    publisher disconnects. The mod's per-slot `if (!peer.active)` gate
    handles the visual teardown on the next frame."""
    buf = struct.pack(_HEADER_FMT, GHOST_MAGIC, VERSION, 0, 0)

    sorted_keys = sorted(peers.keys())

    now = time.monotonic()
    expired_keys: List[str] = []

    written = 0
    for key in sorted_keys:
        if written >= MAX_PEERS:
            break
        peer = peers[key]
        last_seen = peer.get("_last_seen") if isinstance(peer, dict) else None
        if last_seen is not None and (now - last_seen) > PEER_PRESENCE_TIMEOUT_S:
            expired_keys.append(key)
            continue
        # Mid-transition gate: the publisher's player struct reads
        # flags1 == 0 only while a kMapChange is in progress (the
        # struct is in a torn-down state). Pack a zero slot so the
        # mod's `if (!peer.active)` gate tears down the rendered
        # ghost cleanly instead of letting it snap to (0,0,0) at
        # world origin between frames. Pad rather than skip so the
        # slot's array index stays stable across frames (mod's
        # g_slots[i] is keyed by index, not by peer slot id, so
        # shifting other peers down would re-bind the mod render
        # state to the wrong player). Entry stays in the dict —
        # _last_seen is fresh, slot reappears the moment a non-zero
        # flags1 publish lands.
        if isinstance(peer, dict) and int(peer.get("flags1", 1) or 0) == 0:
            buf += b"\x00" * PEER_SIZE
            written += 1
            continue
        try:
            slot = int(key.rsplit("_", 1)[-1])
            r, g, b, a = color_for_slot(slot)

            map_bytes  = (peer.get("map",  "") or "").encode("ascii", errors="replace")[:15]
            anim_bytes = (peer.get("anim", "") or "").encode("ascii", errors="replace")[:16]

            slot_name = peer.get("slot_name", "") or ""
            slot_bytes = slot_name.encode("ascii", errors="replace")[:16]

            paper_agb = peer.get("paper_agb", "") or ""
            paper_agb_bytes = paper_agb.encode("ascii", errors="replace")[:32]

            paper_anim = peer.get("paper_anim", "") or ""
            paper_bytes = paper_anim.encode("ascii", errors="replace")[:16]

            sfx_list = peer.get("sfx_events", []) or []
            sfx_packed = []
            for ev in sfx_list[:SFX_EVENTS_PER_SLOT]:
                if isinstance(ev, dict):
                    sid = int(ev.get("sfx_id", 0)) & 0xFFFF
                    seq = int(ev.get("seq", 0)) & 0xFF
                    flg = int(ev.get("flags", 0)) & 0xFF
                else:
                    sid = int(ev[0]) & 0xFFFF
                    seq = int(ev[1]) & 0xFF
                    flg = int(ev[2]) & 0xFF if len(ev) > 2 else SFX_FLAG_3D
                sfx_packed.extend([sid, seq, flg])
            while len(sfx_packed) < SFX_EVENTS_PER_SLOT * 3:
                sfx_packed.extend([0, 0, 0])
            sfx_count = min(len(sfx_list), SFX_EVENTS_PER_SLOT)

            active_loops_in = peer.get("active_loops", []) or []
            active_loops = []
            for sid in active_loops_in[:ACTIVE_LOOPS_PER_PEER]:
                active_loops.append(int(sid) & 0xFFFF)
            while len(active_loops) < ACTIVE_LOOPS_PER_PEER:
                active_loops.append(0)
            active_loop_count = min(len(active_loops_in), ACTIVE_LOOPS_PER_PEER)

            buf += struct.pack(
                _PEER_FMT,
                1,
                map_bytes.ljust(15,  b"\x00"),
                anim_bytes.ljust(16, b"\x00"),
                float(peer.get("x",     0.0)),
                float(peer.get("y",     0.0)),
                float(peer.get("z",     0.0)),
                float(peer.get("rot_y", 0.0)),
                r, g, b, a,
                int(peer.get("flags2", 0)) & 0xFFFFFFFF,
                int(peer.get("flags3", 0)) & 0xFFFFFFFF,
                int(peer.get("motion_timer", 0)) & 0xFFFF,
                int(peer.get("show_name", 0)) & 0xFF,
                int(peer.get("hammerable", 0)) & 0xFF,
                int(peer.get("team_id", 0)) & 0xFF,
                max(-127, min(127, int(peer.get("spin_dir_hint_y", 0)))),
                max(-127, min(127, int(peer.get("spin_dir_hint_x", 0)))),
                max(-127, min(127, int(peer.get("spin_dir_hint_z", 0)))),
                float(peer.get("camera_angle", 0.0)),
                slot_bytes.ljust(16, b"\x00"),
                paper_agb_bytes.ljust(32, b"\x00"),
                paper_bytes.ljust(16, b"\x00"),
                float(peer.get("rot_x", 0.0)),
                float(peer.get("rot_z", 0.0)),
                float(peer.get("rot_pivot_x", 0.0)),
                float(peer.get("rot_pivot_y", 0.0)),
                float(peer.get("rot_pivot_z", 0.0)),
                float(peer.get("scale_x", 1.0)),
                float(peer.get("scale_y", 1.0)),
                float(peer.get("scale_z", 1.0)),
                float(peer.get("stretch_y", 1.0)),
                int(peer.get("motion_id", 0)) & 0xFFFF,

                float(peer.get("paper_local_time", -1.0)),
                sfx_count & 0xFF,
                active_loop_count & 0xFF,
                0,  # reserved byte (v29 layout pad)
                sfx_packed[0],  sfx_packed[1],  sfx_packed[2],
                sfx_packed[3],  sfx_packed[4],  sfx_packed[5],
                sfx_packed[6],  sfx_packed[7],  sfx_packed[8],
                sfx_packed[9],  sfx_packed[10], sfx_packed[11],
                active_loops[0], active_loops[1], active_loops[2],
                active_loops[3], active_loops[4], active_loops[5],
            )
            written += 1
        except (ValueError, struct.error, TypeError) as e:
            logger.warning(f"Skipping malformed ghost peer {key}: {e}")
            continue

    remaining = MAX_PEERS - written
    if remaining > 0:
        buf += b"\x00" * (remaining * PEER_SIZE)

    for k in expired_keys:
        peers.pop(k, None)

    assert len(buf) == BLOCK_SIZE, f"ghost block sized {len(buf)}, expected {BLOCK_SIZE}"
    return buf

CLEAR_MAGIC = b"\x00" * 4