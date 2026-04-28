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
from dataclasses import dataclass, field
from typing import List, Optional
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
VERSION      = 20           # v20: added `teamId` byte (predefined teams). Slot grew by 4 bytes.

MAX_PEERS    = 32
PEER_SIZE    = 180          # v20: 176 -> 180 (+1 byte teamId, +3 bytes pad to align cameraAngle)
HEADER_SIZE  = 16
BLOCK_SIZE   = HEADER_SIZE + MAX_PEERS * PEER_SIZE   # 5776

# Predefined team IDs. Numeric values stable - both Python and the C++ side
# encode them by value. Stored on the wire in PeerSlot.teamId (u8) and in
# the self-team scratch byte. See GhostPeers.h's kTeam* constants.
TEAM_NONE   = 0
TEAM_RED    = 1
TEAM_BLUE   = 2
TEAM_GREEN  = 3
TEAM_YELLOW = 4

# Map from human-friendly name (lowercased) to numeric team ID. Used by
# the /team command to parse user input.
TEAM_NAMES = {
    "none":   TEAM_NONE,
    "red":    TEAM_RED,
    "blue":   TEAM_BLUE,
    "green":  TEAM_GREEN,
    "yellow": TEAM_YELLOW,
}
# Reverse map for display ("red", "blue", ... or empty for none).
TEAM_LABELS = {
    TEAM_NONE:   "",
    TEAM_RED:    "Red",
    TEAM_BLUE:   "Blue",
    TEAM_GREEN:  "Green",
    TEAM_YELLOW: "Yellow",
}

# Format strings - all big-endian (PowerPC).
# PeerSlot: B 15s 16s ffff BBBB I I H B B f 16s 32s 16s ff fff fff f H 2x f
#   ... + paperLocalTime (float)
# v18: motionTimer's `2x` pad split into `B x` (showName u8 + 1-byte pad).
# v19: that remaining `x` consumed for `hammerable` u8 -> `B B`.
# v20: insert `B 3x` after hammerable for `teamId` u8 + 3-byte pad
#      (to keep cameraAngle aligned to 4 bytes).
# showName:   0 = show name tag for this peer (default; back-compat with
#             v17 zero-pad), 1 = hide.
# hammerable: 0 = can be hammered by other peers (default; back-compat with
#             v18 zero-pad), 1 = opted out via /ghost_hammer.
# teamId:     0 = no team (default), 1=red, 2=blue, 3=green, 4=yellow.
#             Same-team peers skip each other's hits unless /ghost_friendly_fire
#             is on.
# paperLocalTime: animPoseSetLocalTime override for held anims that need
# manual playhead control. The hammer-spin attack (motionId 0x13) holds
# on P_H_1A and mot_hammer2 manually advances the anim time per frame
# from mp+0x2C8 / 6.0. Source publishes that divided value when applicable,
# else 0.0 (sentinel "no override - let pose tick naturally").
_PEER_FMT   = ">B 15s 16s ffff BBBB I I H B B B 3x f 16s 32s 16s ff fff fff f H 2x f"
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
                int(peer.get("show_name", 0)) & 0xFF,   # v18: 0 = show (default), 1 = hide
                int(peer.get("hammerable", 0)) & 0xFF,  # v19: 0 = hammerable (default), 1 = opted out
                int(peer.get("team_id", 0)) & 0xFF,     # v20: 0 = none, 1=red, 2=blue, 3=green, 4=yellow
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
                # -1.0 sentinel = "let the engine tick the playhead
                # naturally". Defaulting to 0.0 would pin every peer's
                # anim to frame 0 each frame and visibly freeze.
                float(peer.get("paper_local_time", -1.0)),
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


# ===========================================================================
# Minigame lobby system
# ===========================================================================
#
# A "lobby" is a logical grouping of players who are playing a shared
# minigame together. Lobbies are scoped to the AP team (you only see and
# interact with peers on your AP team to begin with).
#
# Step 1 (this file): client-side state model + scratch-RAM mirror that
# the mod reads to render an in-game HUD overlay. No cross-player network
# sync yet - lobbies are single-client only. /lobby create makes a
# 1-person lobby visible only to you. Multi-player coordination via AP
# DataStorage comes in a later step.
#
# Architecture:
#   - LobbyState (dataclass) is the source of truth on the Python side.
#   - Commands (/lobby create, /lobby start, etc.) mutate it.
#   - pack_lobby_block() serializes the current state to a fixed-size
#     binary blob the mod reads from kLobbyHudAddress in scratch RAM.
#   - format_lobby_text() renders state to a multi-line string that goes
#     into the free-form text region of the block.
#   - The mod's DrawLobbyHud reads the block, validates magic, and renders
#     header fields + free-form text top-right of screen.
#
# Why structured + free-form instead of just text:
#   The structured header lets the mod render members differently later
#   (color by role, status icons, etc.) without reparsing strings. Right
#   now the mod just renders the text region; the structured part is
#   filled in for future use.

# Lobby HUD scratch address. Single 1KB block at 0x80003D00. Sits past
# the diagnostic block (which ends near 0x80003C90) with breathing room.
LOBBY_HUD_ADDR    = 0x80003D00
LOBBY_HUD_SIZE    = 1024  # 1KB total - header + members + text region

# Magic word at offset 0 - distinguishes "Python wrote here" from "RAM
# garbage at boot." Mod skips drawing if it doesn't match.
LOBBY_HUD_MAGIC   = 0x4C4F4259  # 'LOBY'
LOBBY_HUD_VERSION = 1

# Status enum - what the lobby is currently doing.
LOBBY_STATUS_IDLE      = 0  # no lobby active
LOBBY_STATUS_WAITING   = 1  # in lobby, host hasn't started yet
LOBBY_STATUS_COUNTDOWN = 2  # countdown to game start (timer_seconds counts down)
LOBBY_STATUS_PLAYING   = 3  # game in progress
LOBBY_STATUS_FINISHED  = 4  # game ended, showing results

LOBBY_STATUS_LABELS = {
    LOBBY_STATUS_IDLE:      "Idle",
    LOBBY_STATUS_WAITING:   "Waiting",
    LOBBY_STATUS_COUNTDOWN: "Starting",
    LOBBY_STATUS_PLAYING:   "Playing",
    LOBBY_STATUS_FINISHED:  "Finished",
}

# Game type enum. 0 = none (no game selected). 1 = hide_and_seek (only
# game implemented for now). 2..255 reserved for future minigames.
GAME_TYPE_NONE          = 0
GAME_TYPE_HIDE_AND_SEEK = 1

GAME_TYPE_LABELS = {
    GAME_TYPE_NONE:          "",
    GAME_TYPE_HIDE_AND_SEEK: "Hide and Seek",
}
GAME_TYPE_NAMES = {
    "hide_and_seek": GAME_TYPE_HIDE_AND_SEEK,
    "hide-and-seek": GAME_TYPE_HIDE_AND_SEEK,
    "hns":           GAME_TYPE_HIDE_AND_SEEK,
}

# Role within the lobby. Each member has one of these. The local
# player's role is also published in the header so the mod can render
# "you are X" prominently.
LOBBY_ROLE_NONE      = 0  # not in any lobby
LOBBY_ROLE_HOST      = 1  # owns the lobby; can start/stop/kick
LOBBY_ROLE_PARTICIPANT = 2  # generic participant (used pre-game)
LOBBY_ROLE_HIDER     = 3  # hide_and_seek: hider
LOBBY_ROLE_SEEKER    = 4  # hide_and_seek: seeker
LOBBY_ROLE_SPECTATOR = 5  # eliminated / spectating

LOBBY_ROLE_LABELS = {
    LOBBY_ROLE_NONE:        "",
    LOBBY_ROLE_HOST:        "host",
    LOBBY_ROLE_PARTICIPANT: "ready",
    LOBBY_ROLE_HIDER:       "hider",
    LOBBY_ROLE_SEEKER:      "seeker",
    LOBBY_ROLE_SPECTATOR:   "out",
}

# Maximum members a lobby can hold. Sized to MAX_PEERS so any subset of
# the visible peer set can be in the lobby. Per-member record is 24
# bytes -> 32 * 24 = 768 bytes for the array.
MAX_LOBBY_MEMBERS = MAX_PEERS

# Per-member layout: u8 slot, u8 role, u8 alive, u8 pad, char[16] name,
# u32 reserved -> 24 bytes.
_MEMBER_FMT = ">B B B x 16s 4x"
MEMBER_SIZE = struct.calcsize(_MEMBER_FMT)
assert MEMBER_SIZE == 24, f"member size {MEMBER_SIZE}, expected 24"

# Block layout:
#
#   offset  size  field
#   ------  ----  -----------------------------------------------------
#   0x000   4     magic (u32, 'LOBY')
#   0x004   1     version (u8, 1)
#   0x005   1     active (u8, 0/1)
#   0x006   1     status (u8, LOBBY_STATUS_*)
#   0x007   1     game_type (u8, GAME_TYPE_*)
#   0x008   1     member_count (u8)
#   0x009   1     self_role (u8, LOBBY_ROLE_*)
#   0x00A   2     timer_seconds (u16; 0 = no timer)
#   0x00C   4     reserved
#   0x010   16    lobby_name (char[16])
#   0x020   768   members[32] - each 24 bytes
#   0x320   192   free-form HUD text (NUL-terminated, multi-line via \n)
#   0x3E0   ...   reserved tail
#   0x400         end (1024 bytes)
LOBBY_HEADER_FMT = ">I B B B B B B H I 16s"
LOBBY_HEADER_SIZE = struct.calcsize(LOBBY_HEADER_FMT)
assert LOBBY_HEADER_SIZE == 32, f"lobby header size {LOBBY_HEADER_SIZE}, expected 32"

# Members array starts immediately after the 32-byte header.
LOBBY_MEMBERS_OFFSET = LOBBY_HEADER_SIZE
LOBBY_MEMBERS_END    = LOBBY_MEMBERS_OFFSET + MAX_LOBBY_MEMBERS * MEMBER_SIZE  # 0x320

# Free-form HUD text region. 192 bytes is enough for ~6-8 lines of
# rendered text after the structured header is rendered separately.
LOBBY_TEXT_OFFSET = LOBBY_MEMBERS_END
LOBBY_TEXT_LEN    = 192


@dataclass
class LobbyMember:
    """Single member of a lobby. AP slot id + display name + role."""
    slot: int
    name: str
    role: int = LOBBY_ROLE_PARTICIPANT
    alive: bool = True   # game-specific - hide_and_seek uses this for
                         # "still in" vs "caught/spectating"


@dataclass
class LobbyState:
    """Source of truth for the local client's lobby. Single instance
    per connection, owned by ctx._lobby. None if not in a lobby."""
    lobby_id: str = ""              # unique ID; for step 1, just "<creator>_local"
    name: str = ""                  # human-readable lobby name
    game_type: int = GAME_TYPE_NONE
    status: int = LOBBY_STATUS_IDLE
    members: List[LobbyMember] = field(default_factory=list)
    self_slot: int = 0              # AP slot of the local player
    timer_seconds: int = 0          # 0 = no timer
    # Game-specific extras. Untyped dict for forward extension.
    game_state: dict = field(default_factory=dict)

    def self_member(self) -> Optional[LobbyMember]:
        """Find the LobbyMember corresponding to the local player."""
        for m in self.members:
            if m.slot == self.self_slot:
                return m
        return None

    def is_host(self) -> bool:
        m = self.self_member()
        return m is not None and m.role == LOBBY_ROLE_HOST

    def self_role(self) -> int:
        m = self.self_member()
        return m.role if m else LOBBY_ROLE_NONE


def format_lobby_text(state: LobbyState) -> str:
    """Render the bulk of the lobby HUD as a multi-line string. The
    mod's DrawLobbyHud splits this on \\n and renders each line. Header
    fields (lobby name, game type, status, timer) are rendered by the
    mod from the structured header; this function fills in the member
    list and any game-specific status lines.

    Pure function - safe to call from anywhere; no side effects."""
    lines: List[str] = []

    # Member list. Skip when empty (a fresh-created lobby with one
    # member - the host - still gets listed).
    if state.members:
        lines.append("")  # blank separator after header (which mod renders)
        lines.append("Players:")
        for m in state.members:
            label = LOBBY_ROLE_LABELS.get(m.role, "")
            tag = f" [{label}]" if label else ""
            marker = "" if m.alive else " (out)"
            # "  Mario [host]"
            lines.append(f"  {m.name}{tag}{marker}")

    # Game-specific status lines. Read from game_state dict; if the
    # game type is hide_and_seek, render its standard fields.
    if state.game_type == GAME_TYPE_HIDE_AND_SEEK and state.status == LOBBY_STATUS_PLAYING:
        gs = state.game_state
        round_no = gs.get("round")
        round_total = gs.get("round_total")
        if round_no is not None and round_total is not None:
            lines.append("")
            lines.append(f"Round {round_no}/{round_total}")
        hiders_left = gs.get("hiders_left")
        if hiders_left is not None:
            lines.append(f"Hiders left: {hiders_left}")

    return "\n".join(lines)


def pack_lobby_block(state: Optional[LobbyState]) -> bytes:
    """Serialize the lobby state into the LOBBY_HUD_SIZE-byte payload
    the mod reads. If state is None or status is IDLE, returns a block
    with active=0 (mod skips drawing).

    Returns exactly LOBBY_HUD_SIZE bytes."""
    if state is None or state.status == LOBBY_STATUS_IDLE:
        # Inactive block: header with active=0 plus zero-filled body.
        # Magic is still set so the mod can distinguish "Python wrote
        # but lobby empty" from "uninitialized RAM."
        header = struct.pack(
            LOBBY_HEADER_FMT,
            LOBBY_HUD_MAGIC,
            LOBBY_HUD_VERSION,
            0,                  # active = 0
            LOBBY_STATUS_IDLE,
            GAME_TYPE_NONE,
            0,                  # member_count
            LOBBY_ROLE_NONE,
            0,                  # timer_seconds
            0,                  # reserved
            b"",                # lobby_name (gets NUL-padded to 16)
        )
        return header + b"\x00" * (LOBBY_HUD_SIZE - LOBBY_HEADER_SIZE)

    # Active lobby - pack everything.
    name_bytes = state.name.encode("ascii", errors="replace")[:16]
    self_role = state.self_role()

    header = struct.pack(
        LOBBY_HEADER_FMT,
        LOBBY_HUD_MAGIC,
        LOBBY_HUD_VERSION,
        1,                              # active
        int(state.status) & 0xFF,
        int(state.game_type) & 0xFF,
        min(len(state.members), MAX_LOBBY_MEMBERS) & 0xFF,
        int(self_role) & 0xFF,
        max(0, min(state.timer_seconds, 0xFFFF)) & 0xFFFF,
        0,                              # reserved
        name_bytes.ljust(16, b"\x00"),
    )

    members_buf = b""
    written = 0
    for m in state.members[:MAX_LOBBY_MEMBERS]:
        mname_bytes = (m.name or "").encode("ascii", errors="replace")[:16]
        members_buf += struct.pack(
            _MEMBER_FMT,
            int(m.slot) & 0xFF,
            int(m.role) & 0xFF,
            1 if m.alive else 0,
            mname_bytes.ljust(16, b"\x00"),
        )
        written += 1

    # Pad remaining member slots with zeros.
    if written < MAX_LOBBY_MEMBERS:
        members_buf += b"\x00" * ((MAX_LOBBY_MEMBERS - written) * MEMBER_SIZE)

    # Free-form text region.
    text = format_lobby_text(state)
    text_bytes = text.encode("ascii", errors="replace")[:LOBBY_TEXT_LEN - 1]
    text_buf = text_bytes.ljust(LOBBY_TEXT_LEN, b"\x00")

    # Assemble block.
    buf = header + members_buf + text_buf
    # Pad any remaining tail (reserved area after the text region).
    if len(buf) < LOBBY_HUD_SIZE:
        buf += b"\x00" * (LOBBY_HUD_SIZE - len(buf))

    assert len(buf) == LOBBY_HUD_SIZE, f"lobby block sized {len(buf)}, expected {LOBBY_HUD_SIZE}"
    return buf


# 4-byte clear sentinel: write this to LOBBY_HUD_ADDR to immediately
# stop the HUD without sending a full inactive block. Mod sees magic
# mismatch and skips. Useful on disconnect.
LOBBY_CLEAR_MAGIC = b"\x00" * 4
