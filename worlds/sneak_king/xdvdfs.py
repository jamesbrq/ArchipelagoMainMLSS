"""
xdvdfs.py — Pure Python Xbox DVD Filesystem (XDVDFS/XISO) Reader & Writer

Extracts files from Xbox ISOs and creates new Xbox ISOs from directories.
No external dependencies. MIT-compatible original code.

XDVDFS Format:
  - Sector size: 2048 bytes
  - Volume descriptor at sector 32 (offset 0x10000)
  - Magic: "MICROSOFT*XBOX*MEDIA"
  - Directory entries stored as binary trees
  - Files stored at sector-aligned offsets

Usage:
  # Extract
  iso = XDVDFSImage("game.iso")
  iso.extract_all("output_dir")
  
  # Create
  create_xiso("input_dir", "output.iso")
  
  # Patch in-place (extract, modify files, repack)
  patch_xiso("clean.iso", "patched.iso", {"sneak/default.xbe": "patched_default.xbe"})
"""

import struct
import os
import io
from pathlib import Path

SECTOR_SIZE = 2048
VOLUME_DESCRIPTOR_SECTOR = 32
MAGIC = b"MICROSOFT*XBOX*MEDIA"
MAGIC_LEN = 20

# File attribute flags
ATTR_READONLY  = 0x01
ATTR_HIDDEN    = 0x02
ATTR_SYSTEM    = 0x04
ATTR_DIRECTORY = 0x10
ATTR_ARCHIVE   = 0x20
ATTR_NORMAL    = 0x80


class DirectoryEntry:
    """Represents a file or directory entry in the XDVDFS filesystem."""
    
    def __init__(self, name="", sector=0, size=0, attributes=0):
        self.name = name
        self.sector = sector
        self.size = size
        self.attributes = attributes
        self.children = []  # For directories
        self.left = None    # Binary tree left child (for parsing)
        self.right = None   # Binary tree right child (for parsing)
    
    @property
    def is_directory(self):
        return bool(self.attributes & ATTR_DIRECTORY)
    
    def __repr__(self):
        kind = "DIR" if self.is_directory else "FILE"
        return f"<{kind} '{self.name}' sector={self.sector} size={self.size}>"


class XDVDFSImage:
    """Read and extract files from an Xbox ISO (XDVDFS) image."""
    
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
        """Find the start of the game partition (handles XISO, Redump, and other formats)."""
        file_size = self.f.seek(0, 2)
        
        # Try known offsets where the volume descriptor (sector 32) might be
        known_offsets = [
            0x00000000,     # Standard XISO (trimmed, game data at start)
            0x10000000,     # Common Redump offset (256MB video partition)
            0x18300000,     # Sneak King / BK games Redump offset
            0xFD90000,      # Another Redump variant
        ]
        
        for base in known_offsets:
            vd_offset = base + VOLUME_DESCRIPTOR_SECTOR * SECTOR_SIZE
            if vd_offset + MAGIC_LEN > file_size:
                continue
            try:
                self.f.seek(vd_offset)
                magic = self.f.read(MAGIC_LEN)
                if magic == MAGIC:
                    return base
            except:
                pass
        
        # Fallback: scan the file for the MAGIC string
        # The MAGIC appears at (base + 0x10000), so base = found - 0x10000
        scan_chunk = 16 * 1024 * 1024  # 16MB chunks
        for pos in range(0, min(file_size, 8 * 1024 * 1024 * 1024), scan_chunk):
            try:
                self.f.seek(pos)
                chunk = self.f.read(scan_chunk + MAGIC_LEN)
                idx = chunk.find(MAGIC)
                if idx != -1:
                    found_offset = pos + idx
                    # MAGIC should be at sector 32 of the partition
                    base = found_offset - (VOLUME_DESCRIPTOR_SECTOR * SECTOR_SIZE)
                    if base >= 0:
                        # Verify trailing magic
                        self.f.seek(base + VOLUME_DESCRIPTOR_SECTOR * SECTOR_SIZE + 0x7EC)
                        magic2 = self.f.read(MAGIC_LEN)
                        if magic2 == MAGIC:
                            return base
            except:
                pass
        
        raise ValueError(f"Could not find XDVDFS volume descriptor in {self.path}")
    
    def _read_volume_descriptor(self):
        """Read the volume descriptor and return (root_sector, root_size)."""
        self.f.seek(self.base_offset + VOLUME_DESCRIPTOR_SECTOR * SECTOR_SIZE)
        magic = self.f.read(MAGIC_LEN)
        assert magic == MAGIC, f"Invalid magic: {magic}"
        
        root_sector = struct.unpack("<I", self.f.read(4))[0]
        root_size = struct.unpack("<I", self.f.read(4))[0]
        filetime = struct.unpack("<Q", self.f.read(8))[0]
        
        # Verify trailing magic
        self.f.seek(self.base_offset + VOLUME_DESCRIPTOR_SECTOR * SECTOR_SIZE + 0x7EC)
        magic2 = self.f.read(MAGIC_LEN)
        assert magic2 == MAGIC, f"Trailing magic mismatch: {magic2}"
        
        return root_sector, root_size
    
    def _read_directory(self, sector, size):
        """Read a directory table and return a list of DirectoryEntry objects."""
        if sector == 0 and size == 0:
            return []
        
        self.f.seek(self.base_offset + sector * SECTOR_SIZE)
        data = self.f.read(size)
        
        entries = []
        self._parse_tree(data, 0, entries)
        
        # Recursively read subdirectories
        for entry in entries:
            if entry.is_directory and entry.sector != 0:
                entry.children = self._read_directory(entry.sector, entry.size)
        
        return entries
    
    def _parse_tree(self, data, offset_dwords, entries):
        """Parse the binary tree of directory entries."""
        byte_offset = offset_dwords * 4
        if byte_offset + 14 > len(data):
            return
        
        # Check for empty/padding
        if data[byte_offset] == 0xFF and data[byte_offset + 1] == 0xFF:
            return
        
        left_offset = struct.unpack_from("<H", data, byte_offset)[0]
        right_offset = struct.unpack_from("<H", data, byte_offset + 2)[0]
        sector = struct.unpack_from("<I", data, byte_offset + 4)[0]
        size = struct.unpack_from("<I", data, byte_offset + 8)[0]
        attributes = data[byte_offset + 12]
        name_len = data[byte_offset + 13]
        
        if name_len == 0 or byte_offset + 14 + name_len > len(data):
            return
        
        name = data[byte_offset + 14:byte_offset + 14 + name_len].decode("ascii", errors="replace")
        
        # Traverse left subtree first (alphabetically smaller)
        if left_offset != 0 and left_offset != 0xFFFF:
            self._parse_tree(data, left_offset, entries)
        
        # Add this entry
        entry = DirectoryEntry(name, sector, size, attributes)
        entries.append(entry)
        
        # Traverse right subtree (alphabetically greater)
        if right_offset != 0 and right_offset != 0xFFFF:
            self._parse_tree(data, right_offset, entries)
    
    def list_files(self, entries=None, prefix=""):
        """List all files recursively."""
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
        """Find a directory entry by path (e.g., 'sneak/default.xbe')."""
        parts = path.replace("\\", "/").strip("/").split("/")
        entries = self.root_entries
        for i, part in enumerate(parts):
            found = None
            for entry in entries:
                if entry.name.lower() == part.lower():
                    found = entry
                    break
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
        """Read the contents of a file entry."""
        self.f.seek(self.base_offset + entry.sector * SECTOR_SIZE)
        return self.f.read(entry.size)
    
    def extract_file(self, entry, output_path):
        """Extract a single file to disk."""
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        data = self.read_file(entry)
        with open(output_path, "wb") as out:
            out.write(data)
    
    def extract_all(self, output_dir, entries=None, prefix=""):
        """Extract all files to a directory."""
        if entries is None:
            entries = self.root_entries
        
        for entry in entries:
            path = os.path.join(output_dir, prefix, entry.name)
            if entry.is_directory:
                os.makedirs(path, exist_ok=True)
                self.extract_all(output_dir, entry.children,
                               os.path.join(prefix, entry.name))
            else:
                os.makedirs(os.path.dirname(path), exist_ok=True)
                self.extract_file(entry, path)


def _build_balanced_tree(entries):
    """
    Build a balanced binary tree from a sorted list of entries.
    Returns a list of (entry, left_idx, right_idx) tuples where indices
    are DWORD offsets in the directory table.
    """
    if not entries:
        return []
    
    # Sort entries alphabetically (case-insensitive, matching Xbox behavior)
    sorted_entries = sorted(entries, key=lambda e: e.name.upper())
    
    # Build balanced BST using recursive median splitting
    nodes = []  # (entry, left_dword_offset, right_dword_offset)
    
    def build(start, end):
        """Build balanced BST, return the DWORD offset of the root node."""
        if start > end:
            return 0  # NULL pointer
        
        mid = (start + end) // 2
        entry = sorted_entries[mid]
        
        # Calculate this node's DWORD offset in the table
        # We need to know where it will be placed — calculate size of all
        # preceding nodes
        node_idx = len(nodes)
        nodes.append(None)  # placeholder
        
        left = build(start, mid - 1)
        right = build(mid + 1, end)
        
        nodes[node_idx] = (entry, left, right)
        return node_idx  # Will be converted to DWORD offset later
    
    build(0, len(sorted_entries) - 1)
    return nodes


def _serialize_directory_table(entries):
    """
    Serialize a list of DirectoryEntry objects into a binary directory table.
    Returns bytes.
    """
    if not entries:
        return b""
    
    nodes = _build_balanced_tree(entries)
    
    # First pass: calculate DWORD offsets for each node
    dword_offsets = []
    current_offset = 0
    for entry, _, _ in nodes:
        dword_offsets.append(current_offset)
        # Entry size: 14 bytes header + name length, padded to DWORD boundary
        entry_size = 14 + len(entry.name.encode("ascii"))
        entry_size = (entry_size + 3) & ~3  # Pad to 4-byte boundary
        current_offset += entry_size // 4
    
    # Second pass: serialize
    buf = io.BytesIO()
    for i, (entry, left_idx, right_idx) in enumerate(nodes):
        left_dword = dword_offsets[left_idx] if left_idx != 0 or i != 0 else 0
        right_dword = dword_offsets[right_idx] if right_idx != 0 or i != 0 else 0
        
        # Fix: the root node (index 0) with left=0 means "no left child"
        # But if index 0 IS the left child, we need its offset
        if left_idx == 0 and i != 0:
            # left_idx=0 could mean "the first node" or "no child"
            # In our tree, 0 means "no child" since build() returns 0 for empty
            left_dword = 0
        elif left_idx != 0:
            left_dword = dword_offsets[left_idx]
        else:
            left_dword = 0
        
        if right_idx != 0:
            right_dword = dword_offsets[right_idx]
        else:
            right_dword = 0
        
        name_bytes = entry.name.encode("ascii")
        
        buf.write(struct.pack("<H", left_dword))
        buf.write(struct.pack("<H", right_dword))
        buf.write(struct.pack("<I", entry.sector))
        buf.write(struct.pack("<I", entry.size))
        buf.write(struct.pack("<B", entry.attributes))
        buf.write(struct.pack("<B", len(name_bytes)))
        buf.write(name_bytes)
        
        # Pad to DWORD boundary
        pad = (4 - ((14 + len(name_bytes)) % 4)) % 4
        buf.write(b'\xFF' * pad)
    
    data = buf.getvalue()
    
    # Pad to sector boundary, fill with 0xFF
    remainder = len(data) % SECTOR_SIZE
    if remainder:
        data += b'\xFF' * (SECTOR_SIZE - remainder)
    
    return data


def _collect_files(root_dir):
    """
    Collect all files and directories from a host directory.
    Returns a list of DirectoryEntry objects with .host_path set.
    """
    entries = []
    for item in sorted(os.listdir(root_dir)):
        full_path = os.path.join(root_dir, item)
        entry = DirectoryEntry(name=item)
        entry.host_path = full_path
        
        if os.path.isdir(full_path):
            entry.attributes = ATTR_DIRECTORY
            entry.children = _collect_files(full_path)
        else:
            entry.attributes = ATTR_ARCHIVE
            entry.size = os.path.getsize(full_path)
        
        entries.append(entry)
    
    return entries


def create_xiso(input_dir, output_path):
    """
    Create an XISO image from a directory.
    
    Args:
        input_dir: Path to directory containing game files
        output_path: Path for the output ISO file
    """
    entries = _collect_files(input_dir)
    
    with open(output_path, "wb") as f:
        # Reserve space for volume descriptor (sectors 0-32)
        # Sector 0-31: empty (zeros)
        # Sector 32: volume descriptor
        f.write(b'\x00' * (VOLUME_DESCRIPTOR_SECTOR * SECTOR_SIZE))
        
        # Write volume descriptor placeholder (will update later)
        vd_offset = f.tell()
        f.write(b'\x00' * SECTOR_SIZE)
        
        # Sector 33 is also part of the volume descriptor area
        f.write(b'\x00' * SECTOR_SIZE)
        
        # Now write directory tables and file data
        # We need to:
        # 1. Calculate all directory table sizes
        # 2. Assign sectors to all files and directories
        # 3. Write everything
        
        next_sector = VOLUME_DESCRIPTOR_SECTOR + 2  # Start after volume descriptor
        
        def assign_sectors(entries, depth=0):
            """Assign sectors to directory tables and files (depth-first)."""
            nonlocal next_sector
            
            # First, serialize this directory's table to know its size
            dir_table = _serialize_directory_table(entries)
            dir_sector = next_sector
            dir_size = len(dir_table)
            next_sector += (dir_size + SECTOR_SIZE - 1) // SECTOR_SIZE
            
            # Assign sectors to files and recurse into subdirectories
            for entry in entries:
                if entry.is_directory:
                    if entry.children:
                        child_sector, child_size = assign_sectors(entry.children, depth + 1)
                        entry.sector = child_sector
                        entry.size = child_size
                    else:
                        entry.sector = 0
                        entry.size = 0
                else:
                    entry.sector = next_sector
                    sectors_needed = (entry.size + SECTOR_SIZE - 1) // SECTOR_SIZE
                    if sectors_needed == 0:
                        sectors_needed = 0
                        entry.sector = 0
                    next_sector += sectors_needed
            
            return dir_sector, dir_size
        
        root_sector, root_size = assign_sectors(entries)
        
        # Now write everything
        f.seek(0)
        f.write(b'\x00' * (VOLUME_DESCRIPTOR_SECTOR * SECTOR_SIZE))
        
        def write_all(entries, assigned_sector):
            """Write directory table and all file data."""
            # Re-serialize directory table (now with correct sectors)
            dir_table = _serialize_directory_table(entries)
            f.seek(assigned_sector * SECTOR_SIZE)
            f.write(dir_table)
            
            # Write file data
            for entry in entries:
                if entry.is_directory:
                    if entry.children and entry.sector != 0:
                        write_all(entry.children, entry.sector)
                else:
                    if entry.sector != 0 and hasattr(entry, 'host_path'):
                        f.seek(entry.sector * SECTOR_SIZE)
                        with open(entry.host_path, "rb") as src:
                            data = src.read()
                            f.write(data)
                            # Pad to sector boundary
                            remainder = len(data) % SECTOR_SIZE
                            if remainder:
                                f.write(b'\x00' * (SECTOR_SIZE - remainder))
        
        write_all(entries, root_sector)
        
        # Write volume descriptor
        f.seek(VOLUME_DESCRIPTOR_SECTOR * SECTOR_SIZE)
        f.write(MAGIC)
        f.write(struct.pack("<I", root_sector))
        f.write(struct.pack("<I", root_size))
        f.write(struct.pack("<Q", 0))  # Filetime (0 = not set)
        # Pad to offset 0x7EC
        current = MAGIC_LEN + 4 + 4 + 8
        f.write(b'\x00' * (0x7EC - current))
        f.write(MAGIC)
        # Pad rest of sector
        remaining = SECTOR_SIZE - 0x7EC - MAGIC_LEN
        f.write(b'\x00' * remaining)
        
        # Pad file to 0x10000 boundary
        file_size = f.tell()
        pad_target = (file_size + 0xFFFF) & ~0xFFFF
        if pad_target > file_size:
            f.seek(pad_target - 1)
            f.write(b'\x00')


def patch_xiso(input_iso, output_iso, file_replacements):
    """
    Create a patched copy of an Xbox ISO, replacing specified files.
    
    Args:
        input_iso: Path to the clean input ISO
        output_iso: Path for the patched output ISO
        file_replacements: Dict of {iso_path: host_file_path}
            e.g., {"sneak/default.xbe": "/path/to/patched_default.xbe"}
    """
    with XDVDFSImage(input_iso) as iso:
        # Extract everything to a temp directory
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            iso.extract_all(tmpdir)
            
            # Apply file replacements
            for iso_path, host_path in file_replacements.items():
                dest = os.path.join(tmpdir, iso_path.replace("/", os.sep))
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                import shutil
                shutil.copy2(host_path, dest)
            
            # Repack
            create_xiso(tmpdir, output_iso)


def patch_xbe_in_iso(input_iso, output_iso, xbe_patches, xbe_path="sneak/default.xbe"):
    """
    Convenience function: extract ISO, patch XBE binary, repack ISO.
    
    Args:
        input_iso: Path to clean input ISO
        output_iso: Path for patched output ISO
        xbe_patches: List of (va, old_bytes, new_bytes) tuples
        xbe_path: Path to XBE within the ISO
    """
    VA_DELTA = 0x10000
    
    with XDVDFSImage(input_iso) as iso:
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            # Extract everything
            iso.extract_all(tmpdir)
            
            # Patch XBE
            xbe_full = os.path.join(tmpdir, xbe_path.replace("/", os.sep))
            with open(xbe_full, "r+b") as f:
                data = bytearray(f.read())
                for va, old, new in xbe_patches:
                    off = va - VA_DELTA
                    actual = bytes(data[off:off+len(old)])
                    assert actual == old, \
                        f"XBE mismatch at VA 0x{va:X}: expected {old.hex()}, got {actual.hex()}"
                    data[off:off+len(new)] = new
                f.seek(0)
                f.write(data)
                f.truncate()
            
            # Repack
            create_xiso(tmpdir, output_iso)


# =============================================================================
# CLI interface
# =============================================================================
if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Xbox DVD Filesystem (XDVDFS) Tool")
        print()
        print("Usage:")
        print(f"  {sys.argv[0]} list <iso>              — List files in ISO")
        print(f"  {sys.argv[0]} extract <iso> <dir>      — Extract ISO to directory")
        print(f"  {sys.argv[0]} create <dir> <iso>       — Create ISO from directory")
        print(f"  {sys.argv[0]} info <iso>               — Show ISO information")
        sys.exit(0)
    
    cmd = sys.argv[1].lower()
    
    if cmd == "list":
        with XDVDFSImage(sys.argv[2]) as iso:
            files = iso.list_files()
            for path, size in files:
                print(f"  {size:>12,d}  {path}")
            print(f"\n  {len(files)} files")
    
    elif cmd == "extract":
        output = sys.argv[3] if len(sys.argv) > 3 else "."
        with XDVDFSImage(sys.argv[2]) as iso:
            print(f"Extracting to {output}...")
            iso.extract_all(output)
            files = iso.list_files()
            print(f"  Extracted {len(files)} files")
    
    elif cmd == "create":
        input_dir = sys.argv[2]
        output_iso = sys.argv[3]
        print(f"Creating {output_iso} from {input_dir}...")
        create_xiso(input_dir, output_iso)
        print("  Done")
    
    elif cmd == "info":
        with XDVDFSImage(sys.argv[2]) as iso:
            print(f"ISO: {sys.argv[2]}")
            print(f"  Base offset: 0x{iso.base_offset:X}")
            print(f"  Root sector: {iso.root_sector}")
            print(f"  Root size: {iso.root_size}")
            files = iso.list_files()
            total_size = sum(s for _, s in files)
            print(f"  Files: {len(files)}")
            print(f"  Total size: {total_size:,d} bytes")
    
    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)
