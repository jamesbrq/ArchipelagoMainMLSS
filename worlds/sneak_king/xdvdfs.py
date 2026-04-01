import struct
import os
import io

SECTOR_SIZE = 2048
VOLUME_DESCRIPTOR_SECTOR = 32
MAGIC = b"MICROSOFT*XBOX*MEDIA"
MAGIC_LEN = 20

ATTR_READONLY  = 0x01
ATTR_HIDDEN    = 0x02
ATTR_SYSTEM    = 0x04
ATTR_DIRECTORY = 0x10
ATTR_ARCHIVE   = 0x20
ATTR_NORMAL    = 0x80


class DirectoryEntry:
    def __init__(self, name="", sector=0, size=0, attributes=0):
        self.name = name
        self.sector = sector
        self.size = size
        self.attributes = attributes
        self.children = []

    @property
    def is_directory(self):
        return bool(self.attributes & ATTR_DIRECTORY)

    def __repr__(self):
        kind = "DIR" if self.is_directory else "FILE"
        return f"<{kind} '{self.name}' sector={self.sector} size={self.size}>"


class XDVDFSImage:
    def __init__(self, path):
        self.path = path
        self.f = open(path, "rb")
        self.base_offset = self._find_game_partition()
        self.root_sector, self.root_size = self._read_volume_descriptor()
        self.root_entries = self._read_directory(self.root_sector, self.root_size)

    def close(self):
        self.f.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


    def _find_game_partition(self):
        file_size = self.f.seek(0, 2)
        for base in [0x00000000, 0x10000000, 0x18300000, 0x0FD90000]:
            vd_offset = base + VOLUME_DESCRIPTOR_SECTOR * SECTOR_SIZE
            if vd_offset + MAGIC_LEN > file_size:
                continue
            try:
                self.f.seek(vd_offset)
                if self.f.read(MAGIC_LEN) == MAGIC:
                    return base
            except OSError:
                pass
        # Fallback: brute-force scan
        chunk_sz = 16 * 1024 * 1024
        for pos in range(0, min(file_size, 8 * 1024 * 1024 * 1024), chunk_sz):
            try:
                self.f.seek(pos)
                chunk = self.f.read(chunk_sz + MAGIC_LEN)
                idx = chunk.find(MAGIC)
                if idx != -1:
                    base = pos + idx - VOLUME_DESCRIPTOR_SECTOR * SECTOR_SIZE
                    if base >= 0:
                        self.f.seek(base + VOLUME_DESCRIPTOR_SECTOR * SECTOR_SIZE + 0x7EC)
                        if self.f.read(MAGIC_LEN) == MAGIC:
                            return base
            except OSError:
                pass
        raise ValueError(f"Could not find XDVDFS volume descriptor in {self.path}")

    def _read_volume_descriptor(self):
        self.f.seek(self.base_offset + VOLUME_DESCRIPTOR_SECTOR * SECTOR_SIZE)
        magic = self.f.read(MAGIC_LEN)
        assert magic == MAGIC, f"Invalid magic: {magic}"
        root_sector = struct.unpack("<I", self.f.read(4))[0]
        root_size = struct.unpack("<I", self.f.read(4))[0]
        self.f.read(8)  # filetime
        self.f.seek(self.base_offset + VOLUME_DESCRIPTOR_SECTOR * SECTOR_SIZE + 0x7EC)
        assert self.f.read(MAGIC_LEN) == MAGIC, "Trailing magic mismatch"
        return root_sector, root_size


    def _read_directory(self, sector, size):
        if sector == 0 and size == 0:
            return []
        self.f.seek(self.base_offset + sector * SECTOR_SIZE)
        data = self.f.read(size)
        entries = []
        self._parse_tree(data, 0, entries)
        for entry in entries:
            if entry.is_directory and entry.sector != 0:
                entry.children = self._read_directory(entry.sector, entry.size)
        return entries

    def _parse_tree(self, data, offset_dwords, entries):
        byte_offset = offset_dwords * 4
        if byte_offset + 14 > len(data):
            return
        if data[byte_offset] == 0xFF and data[byte_offset + 1] == 0xFF:
            return
        left = struct.unpack_from("<H", data, byte_offset)[0]
        right = struct.unpack_from("<H", data, byte_offset + 2)[0]
        sector = struct.unpack_from("<I", data, byte_offset + 4)[0]
        size = struct.unpack_from("<I", data, byte_offset + 8)[0]
        attributes = data[byte_offset + 12]
        name_len = data[byte_offset + 13]
        if name_len == 0 or byte_offset + 14 + name_len > len(data):
            return
        name = data[byte_offset + 14 : byte_offset + 14 + name_len].decode("ascii", errors="replace")
        if left != 0 and left != 0xFFFF:
            self._parse_tree(data, left, entries)
        entries.append(DirectoryEntry(name, sector, size, attributes))
        if right != 0 and right != 0xFFFF:
            self._parse_tree(data, right, entries)


    def list_files(self, entries=None, prefix=""):
        if entries is None:
            entries = self.root_entries
        result = []
        for entry in entries:
            path = f"{prefix}{entry.name}"
            if entry.is_directory:
                result.extend(self.list_files(entry.children, path + "/"))
            else:
                result.append((path, entry.size))
        return result

    def find_entry(self, path):
        parts = path.replace("\\", "/").strip("/").split("/")
        entries = self.root_entries
        for i, part in enumerate(parts):
            found = next((e for e in entries if e.name.lower() == part.lower()), None)
            if found is None:
                return None
            if i < len(parts) - 1:
                if not found.is_directory:
                    return None
                entries = found.children
            else:
                return found
        return None

    def read_file(self, entry):
        self.f.seek(self.base_offset + entry.sector * SECTOR_SIZE)
        return self.f.read(entry.size)

    def extract_file(self, entry, output_path):
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "wb") as out:
            out.write(self.read_file(entry))

    def extract_all(self, output_dir, entries=None, prefix=""):
        if entries is None:
            entries = self.root_entries
        for entry in entries:
            path = os.path.join(output_dir, prefix, entry.name)
            if entry.is_directory:
                os.makedirs(path, exist_ok=True)
                self.extract_all(output_dir, entry.children, os.path.join(prefix, entry.name))
            else:
                os.makedirs(os.path.dirname(path), exist_ok=True)
                self.extract_file(entry, path)


class _AVLNode:
    __slots__ = ("entry", "left", "right", "skew")

    def __init__(self, entry):
        self.entry = entry
        self.left = None
        self.right = None
        self.skew = 0  # -1 left-heavy, 0 balanced, 1 right-heavy


def _avl_compare(a, b):
    au, bu = a.upper(), b.upper()
    return -1 if au < bu else (1 if au > bu else 0)


def _avl_rotate_left(root):
    nr = root.right;  root.right = nr.left;  nr.left = root
    return nr


def _avl_rotate_right(root):
    nr = root.left;  root.left = nr.right;  nr.right = root
    return nr


def _avl_insert(root, node):
    if root is None:
        return node, True
    cmp = _avl_compare(node.entry.name, root.entry.name)
    if cmp < 0:
        root.left, grew = _avl_insert(root.left, node)
        if grew:
            if   root.skew ==  1: root.skew = 0; grew = False
            elif root.skew ==  0: root.skew = -1
            else:
                if root.left.skew == -1:
                    root = _avl_rotate_right(root);  root.right.skew = 0
                else:
                    root.left = _avl_rotate_left(root.left)
                    root = _avl_rotate_right(root)
                    root.left.skew  = -1 if root.skew ==  1 else 0
                    root.right.skew =  1 if root.skew == -1 else 0
                root.skew = 0; grew = False
    else:
        root.right, grew = _avl_insert(root.right, node)
        if grew:
            if   root.skew == -1: root.skew = 0; grew = False
            elif root.skew ==  0: root.skew = 1
            else:
                if root.right.skew == 1:
                    root = _avl_rotate_left(root);  root.left.skew = 0
                else:
                    root.right = _avl_rotate_right(root.right)
                    root = _avl_rotate_left(root)
                    root.right.skew = -1 if root.skew ==  1 else 0
                    root.left.skew  =  1 if root.skew == -1 else 0
                root.skew = 0; grew = False
    return root, grew


def _avl_prefix(node):
    if node is None:
        return []
    return [node] + _avl_prefix(node.left) + _avl_prefix(node.right)


def _build_balanced_tree(entries):
    if not entries:
        return []
    avl_root = None
    for entry in entries:
        avl_root, _ = _avl_insert(avl_root, _AVLNode(entry))
    nodes = _avl_prefix(avl_root)
    idx = {id(n): i for i, n in enumerate(nodes)}
    return [(n.entry,
             idx[id(n.left)]  if n.left  else 0,
             idx[id(n.right)] if n.right else 0) for n in nodes]


def _serialize_directory_table(entries):
    if not entries:
        return b"", 0

    nodes = _build_balanced_tree(entries)

    # -- pass 1: compute byte offset for every node --------------------------
    byte_offsets = []
    pos = 0
    for entry, _, _ in nodes:
        entry_len = (14 + len(entry.name.encode("ascii")) + 3) & ~3
        old_sec = (pos + SECTOR_SIZE - 1) // SECTOR_SIZE if pos else 0
        new_sec = (pos + entry_len + SECTOR_SIZE - 1) // SECTOR_SIZE
        if new_sec > old_sec and pos % SECTOR_SIZE:
            pos += (SECTOR_SIZE - pos % SECTOR_SIZE) % SECTOR_SIZE
        byte_offsets.append(pos)
        pos += entry_len

    actual_size = pos
    dword_offsets = [o // 4 for o in byte_offsets]

    # -- pass 2: write bytes -------------------------------------------------
    buf = io.BytesIO()
    wpos = 0
    for i, (entry, li, ri) in enumerate(nodes):
        target = byte_offsets[i]
        if wpos < target:
            buf.write(b"\xFF" * (target - wpos))
            wpos = target
        name_bytes = entry.name.encode("ascii")
        buf.write(struct.pack("<H", 0 if li == 0 else dword_offsets[li]))
        buf.write(struct.pack("<H", 0 if ri == 0 else dword_offsets[ri]))
        buf.write(struct.pack("<I", entry.sector))
        buf.write(struct.pack("<I", entry.size))
        buf.write(struct.pack("<B", entry.attributes))
        buf.write(struct.pack("<B", len(name_bytes)))
        buf.write(name_bytes)
        pad = (4 - ((14 + len(name_bytes)) % 4)) % 4
        buf.write(b"\xFF" * pad)
        wpos = target + 14 + len(name_bytes) + pad

    data = buf.getvalue()
    if len(data) % SECTOR_SIZE:
        data += b"\xFF" * (SECTOR_SIZE - len(data) % SECTOR_SIZE)
    return data, actual_size


def _collect_files(root_dir):
    """Walk *root_dir* and return a list of ``DirectoryEntry`` objects (with
    ``host_path`` set) suitable for packing into an XISO."""
    entries = []
    for item in sorted(os.listdir(root_dir)):
        full = os.path.join(root_dir, item)
        entry = DirectoryEntry(name=item)
        entry.host_path = full
        if os.path.isdir(full):
            entry.attributes = ATTR_DIRECTORY
            entry.children = _collect_files(full)
        else:
            entry.attributes = ATTR_ARCHIVE
            entry.size = os.path.getsize(full)
        entries.append(entry)
    return entries


def _write_iso9660_volume_descriptors(f, total_sectors):
    """Write a minimal ISO 9660 PVD at sector 16 and a terminator at sector 17.
    Required by xemu to recognise the disc image."""
    pvd = bytearray(SECTOR_SIZE)
    pvd[0] = 0x01;  pvd[1:6] = b"CD001";  pvd[6] = 0x01
    struct.pack_into("<I", pvd, 80, total_sectors)
    struct.pack_into(">I", pvd, 84, total_sectors)
    struct.pack_into("<H", pvd, 120, 1);  struct.pack_into(">H", pvd, 122, 1)
    struct.pack_into("<H", pvd, 124, 1);  struct.pack_into(">H", pvd, 126, 1)
    struct.pack_into("<H", pvd, 128, SECTOR_SIZE)
    struct.pack_into(">H", pvd, 130, SECTOR_SIZE)
    pvd[0xBE:0x32D] = b"\x20" * (0x32D - 0xBE)
    for dt in (0x32D, 0x33F, 0x351, 0x363):
        pvd[dt:dt + 17] = b"0" * 17
        if dt + 17 < SECTOR_SIZE:
            pvd[dt + 17] = 0x00
    pvd[0x366] = 0x01
    f.seek(16 * SECTOR_SIZE);  f.write(pvd)

    vdst = bytearray(SECTOR_SIZE)
    vdst[0] = 0xFF;  vdst[1:6] = b"CD001";  vdst[6] = 0x01
    f.seek(17 * SECTOR_SIZE);  f.write(vdst)

_ROOT_DIRECTORY_SECTOR = 0x108   # 264 — matches extract-xiso

def create_xiso(input_dir, output_path):
    """Create an XISO image from a directory on disk."""
    entries = _collect_files(input_dir)

    with open(output_path, "wb") as f:
        # Sectors 0-33: reserved (zeros)
        f.write(b"\x00" * (VOLUME_DESCRIPTOR_SECTOR + 2) * SECTOR_SIZE)

        next_sector = _ROOT_DIRECTORY_SECTOR

        def assign_sectors(entries, is_root=False):
            nonlocal next_sector
            dir_table, actual_size = _serialize_directory_table(entries)
            dir_sector = next_sector
            next_sector += (len(dir_table) + SECTOR_SIZE - 1) // SECTOR_SIZE
            for entry in entries:
                if entry.is_directory:
                    if entry.children:
                        entry.sector, entry.size = assign_sectors(entry.children)
                    else:
                        entry.sector = entry.size = 0
                else:
                    sectors_needed = (entry.size + SECTOR_SIZE - 1) // SECTOR_SIZE
                    if sectors_needed == 0:
                        entry.sector = 0
                    else:
                        entry.sector = next_sector
                        next_sector += sectors_needed
            return (dir_sector, actual_size) if is_root else (dir_sector, len(dir_table))

        root_sector, root_size = assign_sectors(entries, is_root=True)

        # -- write file data --------------------------------------------------
        f.seek(0);  f.write(b"\x00" * VOLUME_DESCRIPTOR_SECTOR * SECTOR_SIZE)

        def write_all(entries, assigned_sector):
            dir_table, _ = _serialize_directory_table(entries)
            f.seek(assigned_sector * SECTOR_SIZE);  f.write(dir_table)
            for entry in entries:
                if entry.is_directory:
                    if entry.children and entry.sector:
                        write_all(entry.children, entry.sector)
                elif entry.sector and hasattr(entry, "host_path"):
                    f.seek(entry.sector * SECTOR_SIZE)
                    with open(entry.host_path, "rb") as src:
                        data = src.read()
                    f.write(data)
                    rem = len(data) % SECTOR_SIZE
                    if rem:
                        f.write(b"\x00" * (SECTOR_SIZE - rem))

        write_all(entries, root_sector)

        # -- XDVDFS volume descriptor (sector 32) ----------------------------
        f.seek(VOLUME_DESCRIPTOR_SECTOR * SECTOR_SIZE)
        f.write(MAGIC)
        f.write(struct.pack("<I", root_sector))
        f.write(struct.pack("<I", root_size))
        f.write(struct.pack("<Q", 127805472000000000))  # 2005-01-01 filetime
        f.write(b"\x00" * (0x7EC - (MAGIC_LEN + 4 + 4 + 8)))
        f.write(MAGIC)
        f.write(b"\x00" * (SECTOR_SIZE - 0x7EC - MAGIC_LEN))

        # -- 64 KiB alignment ------------------------------------------------
        f.seek(0, 2)
        sz = f.tell()
        target = (sz + 0xFFFF) & ~0xFFFF
        if target > sz:
            f.seek(target - 1);  f.write(b"\x00")

        # -- ISO 9660 descriptors (sectors 16-17) ----------------------------
        f.seek(0, 2)
        _write_iso9660_volume_descriptors(f, f.tell() // SECTOR_SIZE)


def patch_xiso(input_iso, output_iso, file_replacements):
    """Extract *input_iso*, replace files from *file_replacements* dict, repack."""
    import shutil, tempfile
    with XDVDFSImage(input_iso) as iso:
        with tempfile.TemporaryDirectory() as tmpdir:
            iso.extract_all(tmpdir)
            for iso_path, host_path in file_replacements.items():
                dest = os.path.join(tmpdir, iso_path.replace("/", os.sep))
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                shutil.copy2(host_path, dest)
            create_xiso(tmpdir, output_iso)
