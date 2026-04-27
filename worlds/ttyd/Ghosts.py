# ghosts.py
#
# Pure-logic helpers for the ghost peer system. NO dolphin access, NO ctx
# access in this file. Anything that needs Dolphin memory or the AP context
# lives in TTYDClient.py and calls into these helpers with raw arguments.
#
# This split exists for two reasons:
#  1. The shared-memory layout MUST stay in lockstep with GhostPeers.h on
#     the C++ side. Keeping the layout in one focused file makes drift
#     easier to spot in code review.
#  2. Pure functions are unit-testable without mocking Dolphin or AP.

import struct
from CommonClient import logger

# ---------------------------------------------------------------------------
# RAM layout - MUST match GhostPeers.h on the mod side.
# Only one shared block: the peer block (client writes, mod reads). The
# client reads our own player state directly from the game's Player struct
# via marioGetPtr's pointer, so no mod-written self-state block is needed.
# ---------------------------------------------------------------------------
GHOSTS_ADDR  = 0x80001800   # peer block (client writes, mod reads)
                            # v17: moved from 0x80002000

# Self-paper-state struct (mod writes, client reads).
# Mod's UpdateAll inspects local Mario's mp+0x240 (paper pose ID) and, if
# active, calls animPoseGetGroupName to retrieve the AGB name. Result is
# written here as a 32-byte NUL-padded ASCII string. Empty string = not
# in paper mode.
#
# History:
#   v9: widened from 16 to 32 bytes after observing real AGB names like
#       "slit_mdel3_pPlane" (17+ chars) being truncated.
#   v16: relocated from 0x80002820 to 0x80003B20 because 32-peer block
#        previously at 0x80002000 extended to 0x80003610.
#   v17: peer block moved to 0x80001800. Self-paper kept at 0x80003B20
#        (still well past new block end 0x80002E10).
SELF_PAPER_AGB_ADDR = 0x80003B20
SELF_PAPER_AGB_LEN  = 32

GHOST_MAGIC  = 0x47484F53   # 'GHOS'
VERSION      = 17           # v17: peer block moved 0x80002000 -> 0x80001800. PeerSlot layout unchanged.

MAX_PEERS    = 32
PEER_SIZE    = 176          # was 172 in v14; +4 bytes for paperLocalTime
HEADER_SIZE  = 16
BLOCK_SIZE   = HEADER_SIZE + MAX_PEERS * PEER_SIZE   # 5648

# Format strings - all big-endian (PowerPC).
# PeerSlot: B 15s 16s ffff BBBB I I H 2x f 16s 32s 16s ff fff fff f H 2x f
#   ... + paperLocalTime (float)
# paperLocalTime: animPoseSetLocalTime override for held anims that need
# manual playhead control. The hammer-spin attack (motionId 0x13) holds
# on P_H_1A and mot_hammer2 manually advances the anim time per frame
# from mp+0x2C8 / 6.0. Source publishes that divided value when applicable,
# else 0.0 (sentinel "no override - let pose tick naturally").
_PEER_FMT   = ">B 15s 16s ffff BBBB I I H 2x f 16s 32s 16s ff fff fff f H 2x f"
_HEADER_FMT = ">IIII"   # magic, version, reserved0, reserved1

assert struct.calcsize(_PEER_FMT)   == PEER_SIZE,   "peer fmt size mismatch"
assert struct.calcsize(_HEADER_FMT) == HEADER_SIZE, "header fmt size mismatch"


# ---------------------------------------------------------------------------
# Bit masks for the published flags fields. These mirror the C++ side and
# the game's own marioPreDisp / marioMakeDispDir routing.
# ---------------------------------------------------------------------------
FLAGS2_REAR_MASK    = 0x80000000  # set -> rear pose (a_mario_r)
FLAGS2_EFFECTS_MASK = 0x10000000  # set -> effects pose (e_mario)
FLAGS3_LEFT_MASK    = 0x00000200  # set -> facing left (no extra rotation)
FLAGS3_RIGHT_MASK   = 0x00000400  # set -> facing right (apply 180 yaw flip)


# ---------------------------------------------------------------------------
# AP DataStorage key naming.
# ---------------------------------------------------------------------------
KEY_PREFIX = "ttyd_ghost_"

def ghost_key(team: int, slot: int) -> str:
    return f"{KEY_PREFIX}{team}_{slot}"


# ---------------------------------------------------------------------------
# Per-peer color assignment.
# Each remote slot gets a stable, distinct tint so users can tell ghosts
# apart. Alpha is fixed at ~38% (96/255) for a clearly translucent look.
# ---------------------------------------------------------------------------
_PALETTE = [
    (255, 128, 128),  # red
    (128, 255, 128),  # green
    (128, 160, 255),  # blue
    (255, 255, 128),  # yellow
    (255, 128, 255),  # magenta
    (128, 255, 255),  # cyan
    (255, 192, 128),  # orange
    (192, 128, 255),  # purple
]
_GHOST_ALPHA = 96

def color_for_slot(slot: int) -> tuple:
    r, g, b = _PALETTE[slot % len(_PALETTE)]
    return (r, g, b, _GHOST_ALPHA)


# ---------------------------------------------------------------------------
# Peer-table mutation. Caller owns the dict; we just provide the rules for
# how to ingest a server-side update.
# ---------------------------------------------------------------------------
def ingest_peer_update(peers: dict, key: str, value) -> None:
    """Apply one server-side update to the caller's peer dict. Mutates in
    place. `value` is the raw value from the AP package - either a dict
    payload or None (peer cleared their state)."""
    if not key.startswith(KEY_PREFIX):
        return
    if value is None or not isinstance(value, dict):
        peers.pop(key, None)
        return
    peers[key] = value


# ---------------------------------------------------------------------------
# Peer-block packing. Caller hands us their peer dict; we return the exact
# 528-byte payload to write to GHOSTS_ADDR (16-byte header + 8 * 64-byte peers).
# ---------------------------------------------------------------------------
def pack_peer_block(peers: dict) -> bytes:
    """Pack peers (dict of key -> state-dict) into the binary peer block.

    Returns exactly BLOCK_SIZE bytes. Excess peers beyond MAX_PEERS
    are dropped; missing fields default to zero / empty string. Malformed
    individual peers are logged and skipped without breaking the rest of
    the block."""
    buf = struct.pack(_HEADER_FMT, GHOST_MAGIC, VERSION, 0, 0)

    # Sort keys so each peer maps to a stable slot index across calls; this
    # keeps palette colors consistent for any given peer.
    sorted_keys = sorted(peers.keys())

    written = 0
    for key in sorted_keys:
        if written >= MAX_PEERS:
            break
        peer = peers[key]
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

            buf += struct.pack(
                _PEER_FMT,
                1,  # active
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
                float(peer.get("paper_local_time", 0.0)),
            )
            written += 1
        except (ValueError, struct.error, TypeError) as e:
            logger.warning(f"Skipping malformed ghost peer {key}: {e}")
            continue

    # Pad remaining slots with zeros (active=0).
    remaining = MAX_PEERS - written
    if remaining > 0:
        buf += b"\x00" * (remaining * PEER_SIZE)

    assert len(buf) == BLOCK_SIZE, f"ghost block sized {len(buf)}, expected {BLOCK_SIZE}"
    return buf


# Sentinel: a 4-byte "magic cleared" payload the client can write to disable
# rendering immediately on disconnect, without needing to construct a full
# block of zeros.
CLEAR_MAGIC = b"\x00" * 4