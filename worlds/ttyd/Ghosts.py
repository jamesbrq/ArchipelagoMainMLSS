import struct
from dataclasses import dataclass, field
from typing import List, Optional
from CommonClient import logger

# Wire-format / GhostState protocol version. Must match kVersion in
# GhostPeers.h on the C++ side. Bumped to 23 when the layout moved
# from hardcoded low-RAM addresses (0x80001800 + 0x80003B20-0x80003BE4
# + 0x80003D00) to a single heap-allocated GhostState container,
# discovered at runtime via APSettings.ghostStatePtr.
GHOST_MAGIC  = 0x47484F53
VERSION      = 23

# APSettings layout (from StateManager.h on the C++ side). APSettings
# is patched into the ROM at this fixed address; it persists across
# the entire session. The ghostStatePtr field at offset 0x3C is
# populated by mod::ghosts::Init() at game boot and is the entry
# point Python uses to find all ghost-peer scratch.
APSETTINGS_ADDR             = 0x80003220
APSETTINGS_GHOST_STATE_PTR  = APSETTINGS_ADDR + 0x3C  # mod::ghosts::GhostState *

# GhostState struct layout (matches GhostState in GhostPeers.h).
# These are OFFSETS within the GhostState struct, not absolute
# addresses. The base pointer is read at runtime from
# APSETTINGS_GHOST_STATE_PTR. Sub-region addresses are computed
# as `ghost_state_base + <offset>`.

# Peer block (SharedBlock): 16-byte header + 16 PeerSlots.
GS_OFF_PEER_BLOCK = 0x0000

MAX_PEERS    = 16
PEER_SIZE    = 200
HEADER_SIZE  = 16
BLOCK_SIZE   = HEADER_SIZE + MAX_PEERS * PEER_SIZE   # 3216

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

# Lobby HUD block (raw 1024 bytes).
GS_OFF_LOBBY_HUD            = GS_OFF_SFX_RING_EVENTS + SFX_RING_CAPACITY * 4   # 0x0D5C
LOBBY_HUD_SIZE    = 1024

# Total expected GhostState size (for sanity-checking offsets here).
# This is the offset of the field PAST the lobby HUD, i.e. the size.
GS_TOTAL_SIZE = GS_OFF_LOBBY_HUD + LOBBY_HUD_SIZE                  # 0x115C


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
        "lobby_hud":          base + GS_OFF_LOBBY_HUD,
    }

SFX_EVENTS_PER_SLOT = 4
SFX_FLAG_3D = 0x01

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

_PEER_FMT   = ">B 15s 16s ffff BBBB I I H B B B 3x f 16s 32s 16s ff fff fff f H 2x f B 3x HBBHBBHBBHBB"
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

def pack_peer_block(peers: dict) -> bytes:
    """Pack peers (dict of key -> state-dict) into the binary peer block.

    Returns exactly BLOCK_SIZE bytes. Excess peers beyond MAX_PEERS
    are dropped; missing fields default to zero / empty string. Malformed
    individual peers are logged and skipped without breaking the rest of
    the block."""
    buf = struct.pack(_HEADER_FMT, GHOST_MAGIC, VERSION, 0, 0)

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
                sfx_packed[0],  sfx_packed[1],  sfx_packed[2],
                sfx_packed[3],  sfx_packed[4],  sfx_packed[5],
                sfx_packed[6],  sfx_packed[7],  sfx_packed[8],
                sfx_packed[9],  sfx_packed[10], sfx_packed[11],
            )
            written += 1
        except (ValueError, struct.error, TypeError) as e:
            logger.warning(f"Skipping malformed ghost peer {key}: {e}")
            continue

    remaining = MAX_PEERS - written
    if remaining > 0:
        buf += b"\x00" * (remaining * PEER_SIZE)

    assert len(buf) == BLOCK_SIZE, f"ghost block sized {len(buf)}, expected {BLOCK_SIZE}"
    return buf

CLEAR_MAGIC = b"\x00" * 4

LOBBY_HUD_MAGIC   = 0x4C4F4259
LOBBY_HUD_VERSION = 1

LOBBY_STATUS_IDLE      = 0
LOBBY_STATUS_WAITING   = 1
LOBBY_STATUS_COUNTDOWN = 2
LOBBY_STATUS_PLAYING   = 3
LOBBY_STATUS_FINISHED  = 4

LOBBY_STATUS_LABELS = {
    LOBBY_STATUS_IDLE:      "Idle",
    LOBBY_STATUS_WAITING:   "Waiting",
    LOBBY_STATUS_COUNTDOWN: "Starting",
    LOBBY_STATUS_PLAYING:   "Playing",
    LOBBY_STATUS_FINISHED:  "Finished",
}

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

LOBBY_ROLE_NONE      = 0
LOBBY_ROLE_HOST      = 1
LOBBY_ROLE_PARTICIPANT = 2
LOBBY_ROLE_HIDER     = 3
LOBBY_ROLE_SEEKER    = 4
LOBBY_ROLE_SPECTATOR = 5

LOBBY_ROLE_LABELS = {
    LOBBY_ROLE_NONE:        "",
    LOBBY_ROLE_HOST:        "host",
    LOBBY_ROLE_PARTICIPANT: "ready",
    LOBBY_ROLE_HIDER:       "hider",
    LOBBY_ROLE_SEEKER:      "seeker",
    LOBBY_ROLE_SPECTATOR:   "out",
}

MAX_LOBBY_MEMBERS = 32

_MEMBER_FMT = ">B B B x 16s 4x"
MEMBER_SIZE = struct.calcsize(_MEMBER_FMT)
assert MEMBER_SIZE == 24, f"member size {MEMBER_SIZE}, expected 24"

LOBBY_HEADER_FMT = ">I B B B B B B H I 16s"
LOBBY_HEADER_SIZE = struct.calcsize(LOBBY_HEADER_FMT)
assert LOBBY_HEADER_SIZE == 32, f"lobby header size {LOBBY_HEADER_SIZE}, expected 32"

LOBBY_TEXT_LEN    = 192

@dataclass
class LobbyMember:
    """Single member of a lobby. AP slot id + display name + role."""
    slot: int
    name: str
    role: int = LOBBY_ROLE_PARTICIPANT
    alive: bool = True

@dataclass
class LobbyState:
    """Source of truth for the local client's lobby. Single instance
    per connection, owned by ctx._lobby. None if not in a lobby."""
    lobby_id: str = ""
    name: str = ""
    game_type: int = GAME_TYPE_NONE
    status: int = LOBBY_STATUS_IDLE
    members: List[LobbyMember] = field(default_factory=list)
    self_slot: int = 0
    timer_seconds: int = 0

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

    if state.members:
        lines.append("")
        lines.append("Players:")
        for m in state.members:
            label = LOBBY_ROLE_LABELS.get(m.role, "")
            tag = f" [{label}]" if label else ""
            marker = "" if m.alive else " (out)"

            lines.append(f"  {m.name}{tag}{marker}")

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

        header = struct.pack(
            LOBBY_HEADER_FMT,
            LOBBY_HUD_MAGIC,
            LOBBY_HUD_VERSION,
            0,
            LOBBY_STATUS_IDLE,
            GAME_TYPE_NONE,
            0,
            LOBBY_ROLE_NONE,
            0,
            0,
            b"",
        )
        return header + b"\x00" * (LOBBY_HUD_SIZE - LOBBY_HEADER_SIZE)

    name_bytes = state.name.encode("ascii", errors="replace")[:16]
    self_role = state.self_role()

    header = struct.pack(
        LOBBY_HEADER_FMT,
        LOBBY_HUD_MAGIC,
        LOBBY_HUD_VERSION,
        1,
        int(state.status) & 0xFF,
        int(state.game_type) & 0xFF,
        min(len(state.members), MAX_LOBBY_MEMBERS) & 0xFF,
        int(self_role) & 0xFF,
        max(0, min(state.timer_seconds, 0xFFFF)) & 0xFFFF,
        0,
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

    if written < MAX_LOBBY_MEMBERS:
        members_buf += b"\x00" * ((MAX_LOBBY_MEMBERS - written) * MEMBER_SIZE)

    text = format_lobby_text(state)
    text_bytes = text.encode("ascii", errors="replace")[:LOBBY_TEXT_LEN - 1]
    text_buf = text_bytes.ljust(LOBBY_TEXT_LEN, b"\x00")

    buf = header + members_buf + text_buf

    if len(buf) < LOBBY_HUD_SIZE:
        buf += b"\x00" * (LOBBY_HUD_SIZE - len(buf))

    assert len(buf) == LOBBY_HUD_SIZE, f"lobby block sized {len(buf)}, expected {LOBBY_HUD_SIZE}"
    return buf

LOBBY_CLEAR_MAGIC = b"\x00" * 4
