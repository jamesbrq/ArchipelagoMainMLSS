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

# Lobby HUD block (raw 1024 bytes).
GS_OFF_LOBBY_HUD            = GS_OFF_SFX_RING_EVENTS + SFX_RING_CAPACITY * 4   # 0x0E1C
MATCH_HUD_SIZE    = 1024

ACTIVE_LOOPS_PER_PEER = 6
GS_OFF_SELF_ACTIVE_LOOP_COUNT = GS_OFF_LOBBY_HUD + MATCH_HUD_SIZE        # 0x121C
GS_OFF_SELF_ACTIVE_LOOPS      = GS_OFF_SELF_ACTIVE_LOOP_COUNT + 4         # 0x1220

GS_OFF_SELF_GAME_ROLE = GS_OFF_SELF_ACTIVE_LOOPS + ACTIVE_LOOPS_PER_PEER * 2  # 0x122C
# +3 bytes pad to align the next field on a 4-byte boundary.

GS_OFF_SELF_FROZEN          = GS_OFF_SELF_GAME_ROLE + 4                  # 0x1230
GS_OFF_PENDING_TELEPORT_SEQ = GS_OFF_SELF_FROZEN + 1                     # 0x1231
# +2 bytes pad at 0x1232-0x1233 so map[16] sits 4-byte aligned.
GS_OFF_PENDING_TELEPORT_MAP  = GS_OFF_SELF_FROZEN + 4                    # 0x1234
GS_OFF_PENDING_TELEPORT_BERO = GS_OFF_PENDING_TELEPORT_MAP + 16          # 0x1244

# Total expected GhostState size (for sanity-checking offsets here).
GS_TOTAL_SIZE = GS_OFF_PENDING_TELEPORT_BERO + 16                        # 0x1254 (4692)


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
        "self_active_loop_count": base + GS_OFF_SELF_ACTIVE_LOOP_COUNT,
        "self_active_loops":      base + GS_OFF_SELF_ACTIVE_LOOPS,
        "self_game_role":         base + GS_OFF_SELF_GAME_ROLE,
        "self_frozen":            base + GS_OFF_SELF_FROZEN,
        "pending_teleport_seq":   base + GS_OFF_PENDING_TELEPORT_SEQ,
        "pending_teleport_map":   base + GS_OFF_PENDING_TELEPORT_MAP,
        "pending_teleport_bero":  base + GS_OFF_PENDING_TELEPORT_BERO,
    }

SFX_EVENTS_PER_SLOT = 4
SFX_FLAG_3D = 0x01
# Note: v25's SFX_FLAG_STOP removed. v26 uses state-sync (peer.activeLoops)
# instead of stop events for loop termination.

GAME_ROLE_NONE   = 0
GAME_ROLE_HIDER  = 1
GAME_ROLE_SEEKER = 2

GAME_ROLE_LABELS = {
    GAME_ROLE_NONE:   "",
    GAME_ROLE_HIDER:  "hider",
    GAME_ROLE_SEEKER: "seeker",
}

GAME_ROLE_NAMES = {
    "none":   GAME_ROLE_NONE,
    "hider":  GAME_ROLE_HIDER,
    "seeker": GAME_ROLE_SEEKER,
}

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
# leaving a sittable decoy when a hider goes AFK.
PEER_PRESENCE_TIMEOUT_S = 4.0

def stamp_peer(peer: dict) -> None:
    """Mark `peer` as freshly observed. Called from ingest paths and
    from any local synthesizer that writes into ctx._ghost_peers
    (solo bots, /ghost_test loopback)."""
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
                int(peer.get("game_role", GAME_ROLE_NONE)) & 0xFF,
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

MATCH_HUD_MAGIC   = 0x4C4F4259
MATCH_HUD_VERSION = 1

MATCH_STATUS_IDLE      = 0
MATCH_STATUS_HIDE   = 1
MATCH_STATUS_SEEK = 2
MATCH_STATUS_ROUND_OVER   = 3
MATCH_STATUS_END  = 4

MATCH_STATUS_LABELS = {
    MATCH_STATUS_IDLE:       "Idle",
    MATCH_STATUS_HIDE:       "Hide",
    MATCH_STATUS_SEEK:       "Seek",
    MATCH_STATUS_ROUND_OVER: "Round Over",
    MATCH_STATUS_END:        "Match End",
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

MATCH_ROLE_NONE      = 0
MATCH_ROLE_NONE      = 1
MATCH_ROLE_NONE = 2
MATCH_ROLE_HIDER     = 3
MATCH_ROLE_SEEKER    = 4
MATCH_ROLE_NONE = 5

MATCH_ROLE_LABELS = {
    MATCH_ROLE_NONE:   "",
    MATCH_ROLE_HIDER:  "hider",
    MATCH_ROLE_SEEKER: "seeker",
}

MAX_MATCH_MEMBERS = 32

MATCH_KEY_PREFIX = "ttyd_match_"

def match_key(team: int) -> str:
    """The AP DataStorage key holding this team's canonical match
    state. One key per team — the team IS the match container."""
    return f"{MATCH_KEY_PREFIX}{team}"

def parse_match_key(key: str) -> Optional[int]:
    """Inverse of match_key. Returns the team id, or None if not a match key."""
    if not key.startswith(MATCH_KEY_PREFIX):
        return None
    rest = key[len(MATCH_KEY_PREFIX):]
    try:
        return int(rest)
    except ValueError:
        return None
    rest = key[len(MATCH_KEY_PREFIX):]
    parts = rest.split("_")
    if len(parts) != 2:
        return None
    try:
        return int(parts[0]), int(parts[1])
    except ValueError:
        return None


# Defaults chosen to make a 5-player hide-and-seek match feel right.
# hide_phase_seconds=0 is the "manual" sentinel — the conductor
# advances HIDE -> SEEK via /hns next once everyone's hidden, instead
# of an auto-countdown. round_time_limit_seconds=180 (3 min) keeps SEEK
# bounded so a stalled chase doesn't hang the match.
DEFAULT_ROUND_COUNT             = 5
DEFAULT_HIDE_PHASE_SECONDS      = 0
DEFAULT_ROUND_TIME_LIMIT_SEC    = 180
# `seeker_count_threshold`: <threshold members -> 1 seeker; else 2.
# 5 puts the boundary at "1 seeker for 4-player lobbies, 2 for 5+".
DEFAULT_SEEKER_COUNT_THRESHOLD  = 5


# Story-advance preset applied at the start of every match. Pins the
# save-file state so round-start `seqSetSeq(kMapChange, ...)` drops
# every member into a clean post-progression state regardless of
# their actual save progress. Used by:
#   - _begin_match (auto-fired at round 1 start)
#   - /hns story (no-args manual apply for testing)
#
# Values are placeholders pending verification against a clean
# known-good save (diff a fresh save against post-Chapter-N save +
# replace these with the diff). Adjust as you collect real values.
HNS_STORY_GSW_VALUES: Dict[int, int] = {i: 99 for i in range(1700, 1721)}
HNS_STORY_GSWF_SET_BITS: List[int] = list(range(6000, 6201)) + [1188, 1213, 1216, 1488, 1489, 1490, 1496, 1926, 2228, 2231, 2436, 2437, 2500, 2832, 2834, 2841, 2865, 2979, 3575, 3726, 4191, 4192, 4193, 4355, 4359, ]
HNS_STORY_GSWF_CLEAR_BITS: List[int] = []


BUILTIN_MAPS: Dict[str, tuple] = {
    "rogueport":      ("gor_01",   "s_bero"),
    "petalburg":      ("nok_00",   "w_bero"),
    "petal_meadows":  ("hei_00",   "dokan_2"),
    "hooktail":       ("gon_00",   "w_bero"),
    "boggly_woods":   ("win_06",   "dokan1"),    # not a typo - no underscore
    "great_tree":     ("mri_00",   "w_bero"),
    "glitzville":     ("tou_01",   ""),          # null bero -> blimp default
    "twilight_town":  ("usu_00",   "dokan_1"),
    "twilight_trail": ("gra_00",   "w_bero"),
    "creepy_steeple": ("gra_06",   "sw_bero"),
    "keelhaul_key":   ("muj_00",   "e_bero"),
    "pirates_grotto": ("muj_05",   "w_bero"),
    "riverside":      ("hom_00",   "n_bero_1"),
    "excess_express": ("rsh_01_a", "s_bero"),
    "poshley":        ("pik_00",   "n_bero"),
    "fahr_outpost":   ("bom_01",   "w_bero"),
    "moon":           ("moo_00",   ""),          # null bero -> first-landing
    "xnaut_fortress": ("aji_19",   "w_bero"),
    "palace_shadow":  ("las_00",   "w_bero"),
    "sewers":         ("tik_01",   "dokan_2"),
}


def resolve_map_entry(name: str) -> Optional[tuple]:
    """Take either a builtin short name like 'rogueport' or a raw
    'map_id:bero_id' string, return (map_id, bero_id) or None on
    obviously-invalid input. A bare map id with no colon is allowed
    (returns empty bero - engine uses default spawn) but most
    gameplay maps need a real bero."""
    s = (name or "").strip()
    if not s:
        return None
    if s in BUILTIN_MAPS:
        return BUILTIN_MAPS[s]
    if ":" in s:
        m, b = s.split(":", 1)
        m = m.strip()
        b = b.strip()
        if m:
            return (m, b)
        return None
    return (s, "")


def encode_map_pool_entry(map_id: str, bero: str) -> str:
    """Inverse of resolve_map_entry's output for storage in
    settings.map_pool. Used by /hns maps add to record an entry in
    the canonical wire format."""
    if bero:
        return f"{map_id}:{bero}"
    return map_id

MATCH_SETTING_BOUNDS = {
    "round_count":                (1,  20),
    # 0 = manual (conductor advances HIDE -> SEEK via /hns next).
    "hide_phase_seconds":         (0,  600),
    "round_time_limit_seconds":   (30, 1800),
    "seeker_count_threshold":     (2,  16),
}

@dataclass
class MatchSettings:
    """Host-tunable knobs. Replicated to all members via the lobby
    state's network dict so everyone sees consistent values."""
    round_count:               int = DEFAULT_ROUND_COUNT
    hide_phase_seconds:        int = DEFAULT_HIDE_PHASE_SECONDS
    round_time_limit_seconds:  int = DEFAULT_ROUND_TIME_LIMIT_SEC
    seeker_count_threshold:    int = DEFAULT_SEEKER_COUNT_THRESHOLD
    map_pool:                  List[str] = field(default_factory=list)

def default_match_settings() -> MatchSettings:
    # Seed with every verified builtin map so /hns maps remove and
    # /hns maps clear operate on a known starting set. Empty out via
    # /hns maps clear if you want a custom pool from scratch.
    return MatchSettings(map_pool=[
        encode_map_pool_entry(m, b) for (m, b) in BUILTIN_MAPS.values()
    ])

def compute_seeker_count(member_count: int, threshold: int) -> int:
    """Auto-pick seeker count from member count and the lobby's
    threshold setting. <threshold members -> 1 seeker, else 2.
    Always at least 1; capped to member_count - 1 so we never end up
    with all members as seekers and zero hiders."""
    if member_count <= 1:
        return 0
    base = 1 if member_count < max(2, threshold) else 2
    return min(base, max(1, member_count - 1))

def parse_setting_value(name: str, raw: str) -> Any:
    """Parse and validate a setting value from a /lobby set <key> <value>
    invocation. Returns the typed value on success, raises ValueError
    on bad input. The validation is best-effort: callers should still
    clamp to the bounds in MATCH_SETTING_BOUNDS for ints."""
    if name not in MATCH_SETTING_BOUNDS:
        raise ValueError(f"unknown setting '{name}'")
    try:
        v = int(raw)
    except (TypeError, ValueError):
        raise ValueError(f"setting '{name}' expects an integer, got '{raw}'")
    lo, hi = MATCH_SETTING_BOUNDS[name]
    if v < lo or v > hi:
        raise ValueError(f"setting '{name}' must be between {lo} and {hi} (got {v})")
    return v

_MEMBER_FMT = ">B B B x 16s 4x"
MEMBER_SIZE = struct.calcsize(_MEMBER_FMT)
assert MEMBER_SIZE == 24, f"member size {MEMBER_SIZE}, expected 24"

MATCH_HEADER_FMT = ">I B B B B B B H I 16s"
MATCH_HEADER_SIZE = struct.calcsize(MATCH_HEADER_FMT)
assert MATCH_HEADER_SIZE == 32, f"lobby header size {MATCH_HEADER_SIZE}, expected 32"

MATCH_TEXT_LEN    = 192

@dataclass
class MatchMember:
    """Single member of a lobby. AP slot id + display name + role."""
    slot: int
    name: str
    role: int = MATCH_ROLE_NONE
    alive: bool = True

@dataclass
class MatchState:
    """A hide-and-seek match. Always exists when AP is connected; status=IDLE
    means no match is currently running. Per-team — the AP team membership
    IS the match container, so there's no separate lobby concept.

    The conductor (whoever ran /hns start) owns mutations during an active
    match (status != IDLE) and runs the timer task. In IDLE, anyone on the
    team can mutate settings; last-write-wins via AP DataStorage."""
    team: int = 0
    status: int = MATCH_STATUS_IDLE
    members: List[MatchMember] = field(default_factory=list)
    self_slot: int = 0
    timer_seconds: int = 0
    conductor_slot: int = 0
    settings: MatchSettings = field(default_factory=default_match_settings)
    game_state: dict = field(default_factory=dict)
    opted_out: List[int] = field(default_factory=list)

    def is_conductor(self) -> bool:
        return self.self_slot != 0 and self.self_slot == self.conductor_slot

    def self_member(self) -> Optional[MatchMember]:
        for m in self.members:
            if m.slot == self.self_slot:
                return m
        return None

    def find_member(self, slot: int) -> Optional[MatchMember]:
        for m in self.members:
            if m.slot == slot:
                return m
        return None

    def has_member(self, slot: int) -> bool:
        return self.find_member(slot) is not None

    def is_active(self) -> bool:
        return self.status != MATCH_STATUS_IDLE


def format_match_text(state: MatchState) -> str:
    """Render the multi-line text region of the HUD overlay. Pure."""
    lines: List[str] = []
    s = state.settings
    gs = state.game_state or {}

    if state.status == MATCH_STATUS_IDLE:
        lines.append("No match active.")
        lines.append(f"Rounds: {s.round_count}")
        lines.append(f"Hide phase: {s.hide_phase_seconds}s")
        lines.append(f"Round limit: {s.round_time_limit_seconds}s")
        if s.map_pool:
            shown = ", ".join(s.map_pool[:4])
            extra = len(s.map_pool) - 4
            if extra > 0:
                shown += f" (+{extra})"
            lines.append(f"Maps: {shown}")
        else:
            lines.append("Maps: (none set)")
        lines.append("")
        lines.append("Run /hns start to begin")

    elif state.status in (MATCH_STATUS_HIDE, MATCH_STATUS_SEEK):
        round_no = gs.get("round", 1)
        round_total = gs.get("round_total", s.round_count)
        cur_map = gs.get("current_map", "")
        members_role = gs.get("members_role") or {}
        phase_name = "Hide" if state.status == MATCH_STATUS_HIDE else "Seek"
        lines.append(f"Round {round_no}/{round_total}")
        lines.append(f"Phase: {phase_name}")
        # In HIDE-manual mode (hide_phase_seconds == 0) the timer stays
        # at 0 and the auto-advance is gated off — surface that
        # someone needs to advance manually.
        if (state.status == MATCH_STATUS_HIDE
                and state.timer_seconds == 0
                and int(s.hide_phase_seconds) <= 0):
            lines.append("(manual: /hns next when everyone's hidden)")
        if cur_map:
            lines.append(f"Map: {cur_map}")
        def _role(slot):
            return members_role.get(slot) or members_role.get(str(slot))
        hiders = sum(1 for m in state.members if _role(m.slot) == "hider")
        seekers = sum(1 for m in state.members if _role(m.slot) == "seeker")
        lines.append(f"Hiders: {hiders}    Seekers: {seekers}")

    elif state.status == MATCH_STATUS_ROUND_OVER:
        round_no = gs.get("round", 1)
        round_total = gs.get("round_total", s.round_count)
        lines.append(f"Round {round_no}/{round_total} complete")
        if round_no >= round_total:
            lines.append("/hns next for results")
        else:
            lines.append("/hns next for round " + str(round_no + 1))

    elif state.status == MATCH_STATUS_END:
        lines.append("Match Complete!")
        lb = gs.get("leaderboard") or []
        if lb:
            lines.append("")
            lines.append("Leaderboard:")
            for i, entry in enumerate(lb[:10], 1):
                if isinstance(entry, dict):
                    name = entry.get("name", "?")
                    secs = entry.get("seconds", 0)
                else:
                    name = entry[1] if len(entry) > 1 else "?"
                    secs = entry[2] if len(entry) > 2 else 0
                lines.append(f"  {i}. {name}: {int(secs)}s")

    if state.members:
        lines.append("")
        lines.append("Players:")
        members_role = gs.get("members_role") or {}
        SHOW_LIMIT = 5
        visible = state.members[:SHOW_LIMIT]
        for m in visible:
            role = members_role.get(m.slot) or members_role.get(str(m.slot))
            if role == "seeker":
                prefix = "\x01"
            elif role == "hider":
                prefix = "\x02"
            else:
                prefix = ""
            alive_marker     = "" if m.alive else " (out)"
            conductor_marker = ""
            lines.append(f"{prefix}  {m.name}{conductor_marker}{alive_marker}")
        overflow = len(state.members) - SHOW_LIMIT
        if overflow > 0:
            lines.append(f"  (+{overflow} more)")

    return "\n".join(lines)

def pack_match_block(state: Optional[MatchState]) -> bytes:
    """Serialize the match state into the MATCH_HUD_SIZE-byte payload
    the mod reads. If state is None, returns a block with active=0
    (mod skips drawing).

    Returns exactly MATCH_HUD_SIZE bytes."""
    if state is None:
        header = struct.pack(
            MATCH_HEADER_FMT,
            MATCH_HUD_MAGIC,
            MATCH_HUD_VERSION,
            0,
            MATCH_STATUS_IDLE,
            0,
            0,
            MATCH_ROLE_NONE,
            0,
            0,
            b"",
        )
        return header + bytes(MATCH_HUD_SIZE - MATCH_HEADER_SIZE)

    self_member = state.self_member()
    self_role = self_member.role if self_member else MATCH_ROLE_NONE

    name_str = MATCH_STATUS_LABELS.get(state.status, "")
    name_bytes = name_str.encode("ascii", errors="replace")[:16]

    header = struct.pack(
        MATCH_HEADER_FMT,
        MATCH_HUD_MAGIC,
        MATCH_HUD_VERSION,
        1,
        int(state.status) & 0xFF,
        1,
        min(len(state.members), MAX_MATCH_MEMBERS) & 0xFF,
        int(self_role) & 0xFF,
        max(0, min(state.timer_seconds, 0xFFFF)) & 0xFFFF,
        0,
        name_bytes.ljust(16, bytes([0])),
    )

    members_buf = b""
    written = 0
    for m in state.members[:MAX_MATCH_MEMBERS]:
        mname_bytes = (m.name or "").encode("ascii", errors="replace")[:16]
        members_buf += struct.pack(
            _MEMBER_FMT,
            int(m.slot) & 0xFF,
            int(m.role) & 0xFF,
            1 if m.alive else 0,
            mname_bytes.ljust(16, bytes([0])),
        )
        written += 1
    if written < MAX_MATCH_MEMBERS:
        members_buf += bytes((MAX_MATCH_MEMBERS - written) * MEMBER_SIZE)

    text_str = format_match_text(state)
    text_bytes = text_str.encode("ascii", errors="replace")[:MATCH_TEXT_LEN - 1]
    text_buf = text_bytes.ljust(MATCH_TEXT_LEN, bytes([0]))

    buf = header + members_buf + text_buf
    if len(buf) < MATCH_HUD_SIZE:
        buf += bytes(MATCH_HUD_SIZE - len(buf))
    assert len(buf) == MATCH_HUD_SIZE, f"match block sized {len(buf)}, expected {MATCH_HUD_SIZE}"
    return buf

MATCH_CLEAR_MAGIC = b"\x00" * 4


MATCH_NET_VERSION = 1

# Sentinel value for "lobby cleared". Host writes this to its lobby key
# on /lobby leave or disconnect so subscribers know to drop the entry.
MATCH_NET_CLEARED = {"nv": MATCH_NET_VERSION, "cleared": True}

def match_state_to_net_dict(state: "MatchState") -> Dict[str, Any]:
    """Serialize a MatchState into a JSON-able dict for AP DataStorage.
    Conductor publishes; team members receive via SetReply and mirror.
    `self_slot` is recomputed locally on receive."""
    s = state.settings
    return {
        "nv":             MATCH_NET_VERSION,
        "team":           int(state.team),
        "status":         int(state.status),
        "timer":          int(state.timer_seconds),
        "conductor_slot": int(state.conductor_slot),
        "members": [
            {
                "slot":  int(m.slot),
                "name":  m.name or "",
                "role":  int(m.role),
                "alive": bool(m.alive),
            }
            for m in state.members[:MAX_MATCH_MEMBERS]
        ],
        "settings": {
            "round_count":              int(s.round_count),
            "hide_phase_seconds":       int(s.hide_phase_seconds),
            "round_time_limit_seconds": int(s.round_time_limit_seconds),
            "seeker_count_threshold":   int(s.seeker_count_threshold),
            "map_pool":                 list(s.map_pool),
        },
        "game_state": dict(state.game_state or {}),
        "opted_out":  list(state.opted_out),
    }

def match_state_from_net_dict(d: Dict[str, Any], self_slot: int) -> Optional["MatchState"]:
    """Inverse of match_state_to_net_dict. Returns None for cleared
    sentinel or foreign nv. Tolerant of missing keys via defaults."""
    if not isinstance(d, dict):
        return None
    if d.get("cleared") is True:
        return None
    nv = d.get("nv")
    if nv is not None and nv != MATCH_NET_VERSION:
        logger.debug(f"match net dict has unknown nv={nv}, dropping")
        return None

    raw_members = d.get("members") or []
    members: List[MatchMember] = []
    for rm in raw_members[:MAX_MATCH_MEMBERS]:
        if not isinstance(rm, dict):
            continue
        try:
            members.append(MatchMember(
                slot=int(rm.get("slot", 0)),
                name=str(rm.get("name", "") or "")[:16],
                role=int(rm.get("role", MATCH_ROLE_NONE)),
                alive=bool(rm.get("alive", True)),
            ))
        except (TypeError, ValueError):
            continue

    raw_settings = d.get("settings") or {}
    settings = MatchSettings(
        round_count=int(raw_settings.get("round_count", DEFAULT_ROUND_COUNT)),
        hide_phase_seconds=int(raw_settings.get("hide_phase_seconds",
                                                DEFAULT_HIDE_PHASE_SECONDS)),
        round_time_limit_seconds=int(raw_settings.get("round_time_limit_seconds",
                                                      DEFAULT_ROUND_TIME_LIMIT_SEC)),
        seeker_count_threshold=int(raw_settings.get("seeker_count_threshold",
                                                    DEFAULT_SEEKER_COUNT_THRESHOLD)),
        map_pool=[str(m)[:15] for m in (raw_settings.get("map_pool") or []) if m],
    )

    return MatchState(
        team=int(d.get("team", 0)),
        status=int(d.get("status", MATCH_STATUS_IDLE)),
        members=members,
        self_slot=int(self_slot),
        timer_seconds=max(0, min(int(d.get("timer", 0)), 0xFFFF)),
        conductor_slot=int(d.get("conductor_slot", 0)),
        settings=settings,
        game_state=dict(d.get("game_state") or {}),
        opted_out=[int(x) for x in (d.get("opted_out") or [])],
    )
