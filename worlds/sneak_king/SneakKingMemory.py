"""
Sneak King — pymem Memory Helper

Mission visibility bits stored in per-group padding within MissionStateCache:
  Group 0 (Sawmill):      cache+0x38, +0x39, +0x3A  (slots 0-19)
  Group 1 (Construction): cache+0x58, +0x59, +0x5A  (slots 0-19)
  Group 2 (Suburbia):     cache+0x78, +0x79, +0x7A  (slots 0-19)
  Group 3 (Urban):        cache+0x98, +0x99, +0x9A  (slots 0-19)
"""

import struct
import logging
from typing import Optional

logger = logging.getLogger("SneakKingMemory")

try:
    import pymem
    import pymem.memory
    PYMEM_AVAILABLE = True
except ImportError:
    PYMEM_AVAILABLE = False
    logger.warning("pymem not installed")

EMULATOR_NAMES = ["xemu.exe", "xemu-win-release.exe"]

GLOBALS_PAGE_VA   = 0x2E2000
CACHE_PTR_OFFSET  = 0xCCC
WORLD_MGR_OFFSET  = 0xCD0
GAME_STATE_OFFSET = 0xCD8
KING_PTR_OFFSET   = 0xEB8

# King object offsets (from [globals+KING_PTR_OFFSET] → King entity)
KING_INTERACT_PROMPT = 0x258    # u32: 1=near interactable (prompt visible), 0=idle or inside
KING_INTERACTION_PTR = 0x32C    # ptr: entity the King is near/inside (0 when no interactable nearby)

CACHE_VTABLE       = 0x002B8F6C
CACHE_SIZE         = 0xD0
CACHE_GROUP_BASE   = 0x20    # first group starts at cache+0x20
CACHE_GROUP_STRIDE = 32      # 32 bytes per group
CACHE_AP_OFFSET    = 0x18    # padding starts at +0x18 WITHIN each group (bytes 24-26)
CACHE_AP_BYTES     = 3       # 3 bytes per group (24 bits, 20 used)
CACHE_COUNTER      = 0xA0
CACHE_AVAILABILITY = 0xA4
CACHE_DIRTY        = 0xC0

GROUP_NAMES = {0: "Sawmill", 1: "Cul-De-Sac", 2: "Construction", 3: "Downtown"}


def gid_to_group_slot(gid: int) -> tuple[int, int]:
    """GID to (group, slot) per XBE InitFromLevel at 0x626AA."""
    if gid < 20:    return 0, gid           # Sawmill
    elif gid < 40:  return 2, gid - 20      # Construction
    elif gid < 60:  return 1, gid - 40      # Cul-De-Sac
    else:           return 3, gid - 60      # Downtown


def group_slot_to_gid(group: int, slot: int) -> int:
    if group == 0: return slot              # Sawmill
    elif group == 2: return 20 + slot       # Construction
    elif group == 1: return 40 + slot       # Cul-De-Sac
    elif group == 3: return 60 + slot       # Downtown
    return -1


def _cache_offset(group: int, slot: int) -> tuple[int, int]:
    """Return (byte_offset_in_cache, bit_index) for a mission visibility bit."""
    byte_in_group = slot // 8
    bit_in_byte = slot % 8
    offset = CACHE_GROUP_BASE + group * CACHE_GROUP_STRIDE + CACHE_AP_OFFSET + byte_in_group
    return offset, bit_in_byte



class SneakKingMemory:
    def __init__(self):
        self.pm: Optional[object] = None
        self.xbox_base: Optional[int] = None
        self.globals_phys: Optional[int] = None
        self.cache_phys: Optional[int] = None
        self._connected = False

    @property
    def connected(self) -> bool:
        return self._connected and self.pm is not None

    @property
    def cache_loaded(self) -> bool:
        return self.cache_phys is not None

    def connect(self) -> bool:
        if not PYMEM_AVAILABLE:
            logger.error("pymem is not installed")
            return False
        self.pm = None
        for name in EMULATOR_NAMES:
            try:
                self.pm = pymem.Pymem(name)
                logger.info(f"Connected to {name} (PID {self.pm.process_id})")
                break
            except pymem.exception.ProcessNotFound:
                continue
            except Exception as e:
                logger.debug(f"Error connecting to {name}: {e}")
        if self.pm is None:
            logger.error("No emulator process found")
            return False
        self.xbox_base = self._find_xbox_ram()
        if self.xbox_base is None:
            logger.error("Could not find Xbox RAM")
            self._disconnect()
            return False
        logger.info(f"Xbox RAM at 0x{self.xbox_base:X}")
        if not self._find_globals():
            logger.warning("Globals page not found")
            self._connected = True
            return False
        if not self._load_cache():
            logger.warning("Cache not loaded")
            self._connected = True
            return False
        self._connected = True
        return True

    def ensure_ready(self) -> bool:
        if not self._connected:
            return False

        if self.globals_phys is None:
            if not self._find_globals():
                return False
            if not self._load_cache():
                return False
            return True

        if self.cache_phys is not None:
            try:
                vt = self._read_phys_u32(self.cache_phys)
                if vt == CACHE_VTABLE:
                    return True
            except:
                pass
            self.cache_phys = None

        if self.globals_phys is not None:
            if self._load_cache():
                return True
            self.globals_phys = None

        if not self._find_globals():
            return False
        return self._load_cache()

    def disconnect(self):
        self._disconnect()

    def _disconnect(self):
        self._connected = False
        self.globals_phys = None
        self.cache_phys = None
        if self.pm:
            try: self.pm.close_process()
            except: pass
            self.pm = None

    def _find_xbox_ram(self) -> Optional[int]:
        addr = 0
        while addr < 0x7FFFFFFFFFFF:
            try:
                mbi = pymem.memory.virtual_query(self.pm.process_handle, addr)
            except:
                break
            if mbi.State == 0x1000 and mbi.RegionSize >= 64 * 1024 * 1024:
                try:
                    if self.pm.read_bytes(mbi.BaseAddress, 4) == b'\xEF\xBE\xAD\xDE':
                        return mbi.BaseAddress
                except:
                    pass
            addr = mbi.BaseAddress + mbi.RegionSize
        return None

    def _find_globals(self) -> bool:
        """Scan Xbox RAM for the globals page by signature matching.

        Validates candidates by checking that the cache pointer at +0xCCC
        leads to an object with the correct vtable. This prevents false
        positives from pages that happen to have high-VA-like values.
        """
        def is_high_va(v): return 0x83000000 <= v <= 0x87FFFFFF

        for phys in range(0, 0x8000000, 0x1000):
            try:
                page = self.pm.read_bytes(self.xbox_base + phys, 0x1000)
            except:
                continue
            v_cd0 = struct.unpack_from("<I", page, WORLD_MGR_OFFSET)[0]
            if not is_high_va(v_cd0): continue
            v_eb8 = struct.unpack_from("<I", page, KING_PTR_OFFSET)[0]
            if not is_high_va(v_eb8): continue
            v_cd8 = struct.unpack_from("<I", page, GAME_STATE_OFFSET)[0]
            if not is_high_va(v_cd8): continue

            cache_ptr = struct.unpack_from("<I", page, CACHE_PTR_OFFSET)[0]
            if cache_ptr == 0 or cache_ptr < 0x80000000:
                logger.debug(f"Globals candidate at 0x{phys:X}: cache ptr null/invalid (0x{cache_ptr:08X}), skipping")
                continue
            cache_phys = cache_ptr & 0x0FFFFFFF
            try:
                vt = self._read_phys_u32(cache_phys)
            except:
                logger.debug(f"Globals candidate at 0x{phys:X}: can't read cache vtable, skipping")
                continue
            if vt != CACHE_VTABLE:
                logger.debug(f"Globals candidate at 0x{phys:X}: vtable 0x{vt:08X} != 0x{CACHE_VTABLE:08X}, skipping")
                continue

            self.globals_phys = phys
            logger.info(f"Globals page at phys 0x{phys:X} (validated)")
            return True
        return False

    def _load_cache(self) -> bool:
        if self.globals_phys is None: return False
        try:
            cache_ptr = self._read_phys_u32(self.globals_phys + CACHE_PTR_OFFSET)
        except:
            return False
        if cache_ptr == 0 or cache_ptr < 0x80000000: return False
        phys = cache_ptr & 0x0FFFFFFF
        try:
            vt = self._read_phys_u32(phys)
        except:
            return False
        if vt != CACHE_VTABLE:
            logger.debug(f"Cache vtable mismatch: 0x{vt:08X}")
            return False
        self.cache_phys = phys
        logger.info(f"Cache loaded at phys 0x{phys:08X}")
        return True

    def _read_phys(self, phys, size):
        return self.pm.read_bytes(self.xbox_base + phys, size)

    def _write_phys(self, phys, data):
        self.pm.write_bytes(self.xbox_base + phys, data, len(data))

    def _read_phys_u8(self, phys):
        return struct.unpack('B', self._read_phys(phys, 1))[0]

    def _read_phys_u32(self, phys):
        return struct.unpack('<I', self._read_phys(phys, 4))[0]

    def _write_phys_u8(self, phys, val):
        self._write_phys(phys, struct.pack('B', val))

    def _write_phys_u32(self, phys, val):
        self._write_phys(phys, struct.pack('<I', val))

    def read_cache_byte(self, offset):
        return self._read_phys_u8(self.cache_phys + offset)

    def write_cache_byte(self, offset, val):
        self._write_phys_u8(self.cache_phys + offset, val)

    def read_cache_u32(self, offset):
        return self._read_phys_u32(self.cache_phys + offset)

    def write_cache_u32(self, offset, val):
        self._write_phys_u32(self.cache_phys + offset, val)

    def read_cache_bytes(self, offset, size):
        return self._read_phys(self.cache_phys + offset, size)

    def write_cache_bytes(self, offset, data):
        self._write_phys(self.cache_phys + offset, data)

    def read_rank(self, gid):
        g, s = gid_to_group_slot(gid)
        return self.read_cache_byte(CACHE_GROUP_BASE + g * CACHE_GROUP_STRIDE + 4 + s)

    def write_rank(self, gid, rank):
        g, s = gid_to_group_slot(gid)
        self.write_cache_byte(CACHE_GROUP_BASE + g * CACHE_GROUP_STRIDE + 4 + s, rank)

    def read_visible(self, gid):
        g, s = gid_to_group_slot(gid)
        off, bit = _cache_offset(g, s)
        return bool(self.read_cache_byte(off) & (1 << bit))

    def write_visible(self, gid, val=True):
        g, s = gid_to_group_slot(gid)
        off, bit = _cache_offset(g, s)
        b = self.read_cache_byte(off)
        if val:  b |= (1 << bit)
        else:    b &= ~(1 << bit)
        self.write_cache_byte(off, b)

    def set_dirty(self):
        flags = self.read_cache_u32(CACHE_DIRTY)
        self.write_cache_u32(CACHE_DIRTY, flags | 1)

    def _read_king_phys(self) -> Optional[int]:
        """Get the King entity's physical address from the globals page.

        If the King pointer is consistently invalid (junk data), the globals
        page has likely gone stale and needs to be re-scanned.
        """
        if self.globals_phys is None:
            return None
        try:
            king_va = self._read_phys_u32(self.globals_phys + KING_PTR_OFFSET)
            if 0x83000000 <= king_va <= 0x87FFFFFF:
                # Filter out sentinel fill patterns
                if king_va == 0x87878787:
                    return None
                self._king_bad_reads = 0
                return king_va & 0x0FFFFFFF
            else:
                self._king_bad_reads = getattr(self, '_king_bad_reads', 0) + 1
                if self._king_bad_reads <= 3:
                    logger.debug(f"[InteractDbg] King ptr out of range: 0x{king_va:08X}")
                if self._king_bad_reads == 10:
                    logger.info(f"[InteractDbg] King ptr invalid 10x in a row (last: 0x{king_va:08X}), forcing globals re-scan")
                    self.globals_phys = None
                    self.cache_phys = None
        except Exception as e:
            logger.debug(f"[InteractDbg] King ptr read error: {e}")
        return None

    def read_interaction_entity(self) -> Optional[tuple]:
        """Read the current interaction entity pointer and its world position.

        Returns (entity_va, x, y, z) if King is INSIDE an interactable,
        or None if not inside one or read fails.

        Detection logic:
          +0x32C = entity pointer (set when near OR inside)
          +0x258 = prompt flag (1=near/prompt showing, 0=idle or inside)
          Trigger: +0x32C is valid AND +0x258 == 0 → King is INSIDE.

        King+0x32C sometimes points to a child sub-entity rather than the
        parent container. When this happens, entity+0x30 holds a pointer to
        the parent. We walk up the chain (max 4 hops) and return positions
        for each level so the client can try matching any of them.
        """
        king_phys = self._read_king_phys()
        if king_phys is None:
            return None
        try:
            entity_va = self._read_phys_u32(king_phys + KING_INTERACTION_PTR)
            if entity_va == 0 or not (0x83000000 <= entity_va <= 0x87FFFFFF):
                return None

            prompt = self._read_phys_u32(king_phys + KING_INTERACT_PROMPT)
            if prompt != 0:
                return None

            positions = []
            current_va = entity_va
            seen = set()
            for depth in range(5):
                if current_va in seen:
                    break
                seen.add(current_va)
                current_phys = current_va & 0x0FFFFFFF
                pos = self._read_entity_position(current_phys)
                if pos:
                    positions.append((current_va, pos[0], pos[1], pos[2]))
                    logger.debug(f"[InteractDbg] depth={depth} entity=0x{current_va:08X} pos=({pos[0]:.1f}, {pos[1]:.1f}, {pos[2]:.1f})")

                try:
                    parent_va = self._read_phys_u32(current_phys + 0x30)
                    if parent_va == 0 or not (0x83000000 <= parent_va <= 0x87FFFFFF):
                        break
                    if parent_va == current_va:
                        break
                    current_va = parent_va
                except:
                    break

            if not positions:
                return None

            return (entity_va, positions)
        except Exception as e:
            logger.info(f"[InteractDbg] exception: {e}")
            return None

    def _read_entity_position(self, entity_phys: int) -> Optional[tuple]:
        try:
            transform_va = self._read_phys_u32(entity_phys + 0x64)
            if not (0x83000000 <= transform_va <= 0x87FFFFFF):
                return None
            transform_phys = transform_va & 0x0FFFFFFF
            pos_data = self._read_phys(transform_phys + 0x04, 12)
            x, y, z = struct.unpack('<fff', pos_data)
            if abs(x) > 100000 or abs(y) > 100000 or abs(z) > 100000:
                return None
            return (x, y, z)
        except:
            return None

