"""
Sneak King Archipelago ROM Patcher

Uses APProcedurePatch with one procedure:
  patch_xbe — Extract XBE from XISO, apply binary patches from patches.json, repack ISO.

Patch definitions are stored in patches.json for easy editing.
ISO handling uses xdvdfs.py (pure Python, no external dependencies).
"""

import json
import os
import pkgutil
import shutil
import struct
import tempfile

from typing import TYPE_CHECKING

from worlds.Files import APProcedurePatch, APTokenMixin, APPatchExtension

from .xdvdfs import XDVDFSImage, create_xiso

if TYPE_CHECKING:
    from . import SneakKingWorld


VA_DELTA = 0x10000
XBE_MAGIC = b"XBEH"

# XBE section layout for VA-to-file-offset conversion
XBE_SECTIONS = [
    # (va_start, file_offset, size)
    (0x00011000, 0x00001000, 0x1DB5BC),  # .text
    (0x002AFB20, 0x0029B000, 0x01FF2C),  # .rdata
    (0x002CFA60, 0x002BB000, 0x013260),  # .data
]


def va_to_file_offset(va: int) -> int:
    """Convert a Virtual Address to a file offset, handling all XBE sections."""
    for sec_va, sec_file, sec_size in XBE_SECTIONS:
        if sec_va <= va < sec_va + sec_size:
            return va - sec_va + sec_file
    # Fallback: assume .text section delta
    return va - 0x10000


def get_base_rom_as_bytes() -> bytes:
    with open(SneakKingWorld.settings.rom_file, "rb") as f:
        return f.read()


class SneakKingPatchExtension(APPatchExtension):
    game = "Sneak King"

    @staticmethod
    def patch_xbe(caller: APProcedurePatch, rom: bytes) -> bytes:
        """Extract XBE from XISO, apply all binary patches, repack and return new ISO bytes."""
        patch_data = pkgutil.get_data(__name__, "data/patches.json")
        if patch_data is None:
            raise FileNotFoundError("Missing patches.json in APWorld")
        patches = json.loads(patch_data.decode("utf-8"))

        xbe_path = patches["xbe_file"]
        expected_size = patches["expected_xbe_size"]

        tmpdir = tempfile.mkdtemp()
        try:
            # Write source ISO bytes to a temp file so XDVDFSImage can open it
            source_path = os.path.join(tmpdir, "source.iso")
            with open(source_path, "wb") as f:
                f.write(rom)

            # Extract all files from source ISO
            extracted_files: dict[str, bytes] = {}
            with XDVDFSImage(source_path) as iso:
                for path, _size in iso.list_files():
                    entry = iso.find_entry(path)
                    if entry is not None:
                        extracted_files[path] = iso.read_file(entry)

            # Delete source ISO immediately — no longer needed
            os.remove(source_path)

            if xbe_path not in extracted_files:
                raise FileNotFoundError(f"Could not find {xbe_path} in ISO")

            xbe_data = bytearray(extracted_files[xbe_path])

            # Validate XBE
            if len(xbe_data) != expected_size:
                raise ValueError(
                    f"XBE size mismatch: {len(xbe_data)} (expected {expected_size}). "
                    f"Is this the correct Sneak King ROM?"
                )
            if xbe_data[:4] != XBE_MAGIC:
                raise ValueError("Invalid XBE: missing XBEH magic")

            # Apply required patches (byte replacement at VA offsets)
            for patch in patches["patches"]["required"]:
                va = int(patch["va"], 16)
                old = bytes.fromhex(patch["old"])
                new = bytes.fromhex(patch["new"])
                offset = va_to_file_offset(va)

                actual = bytes(xbe_data[offset:offset + len(old)])
                if actual != old:
                    raise ValueError(
                        f"Patch '{patch['name']}' failed at VA {patch['va']}: "
                        f"expected {patch['old']}, found {actual.hex()}. "
                        f"ROM may already be patched or is wrong version."
                    )
                xbe_data[offset:offset + len(new)] = new

            # Apply settings-driven patches (values come from player options)
            seed_options = json.loads(caller.get_file("options.json").decode("utf-8"))

            for patch in patches["patches"].get("settings", []):
                va = int(patch["va"], 16)
                offset = va_to_file_offset(va)
                option_key = patch["option"]
                mode = patch.get("mode", "set")

                if mode == "multiply":
                    base = patch["base"]
                    multiplier = seed_options.get(option_key, 1.0)
                    value = base * multiplier
                elif mode == "divide":
                    base = patch["base"]
                    divisor = seed_options.get(option_key, 1.0)
                    value = base / divisor if divisor != 0 else base
                elif mode == "map":
                    map_name = patch["map_name"]
                    mapping = patches.get(map_name, {})
                    raw_value = seed_options.get(option_key, 0)
                    value = mapping.get(str(raw_value), raw_value)
                else:
                    value = seed_options.get(option_key, patch.get("default", 0))

                if patch["type"] == "float":
                    xbe_data[offset:offset + 4] = struct.pack("<f", value)
                elif patch["type"] == "byte":
                    xbe_data[offset] = int(value) & 0xFF
                elif patch["type"] == "word":
                    xbe_data[offset:offset + 2] = struct.pack("<H", int(value) & 0xFFFF)
                elif patch["type"] == "dword":
                    xbe_data[offset:offset + 4] = struct.pack("<I", int(value) & 0xFFFFFFFF)
                elif patch["type"] == "raw":
                    raw_bytes = bytes.fromhex(value)
                    xbe_data[offset:offset + len(raw_bytes)] = raw_bytes

            extracted_files[xbe_path] = bytes(xbe_data)

            # Write all files to a staging dir and repack into a new ISO
            stage_dir = os.path.join(tmpdir, "stage")
            for path, data in extracted_files.items():
                full_path = os.path.join(stage_dir, path.replace("/", os.sep))
                os.makedirs(os.path.dirname(full_path), exist_ok=True)
                with open(full_path, "wb") as f:
                    f.write(data)

            output_path = os.path.join(tmpdir, "output.iso")
            create_xiso(stage_dir, output_path)

            # Read output into memory, then delete it before returning
            with open(output_path, "rb") as f:
                result = f.read()
            os.remove(output_path)

            return result
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)


class SneakKingProcedurePatch(APProcedurePatch):
    game = "Sneak King"
    patch_file_ending = ".apsk"
    result_file_ending = ".iso"

    procedure = [
        ("patch_xbe", []),
    ]

    @classmethod
    def get_source_data(cls) -> bytes:
        return get_base_rom_as_bytes()


def write_files(world: "SneakKingWorld", patch: SneakKingProcedurePatch) -> None:
    """
    Called by the Archipelago world generator to write seed-specific data
    into the patch file. This runs on the server during generation.
    """
    options_dict = {
        "seed": world.multiworld.seed,
        "seed_name": world.multiworld.seed_name,
        "player": world.player,
        "player_name": world.multiworld.player_name[world.player],
        # Settings-driven patch values (keys match "option" in patches.json)
        "starting_level": world.options.starting_level.value,
        "king_speed_multiplier": world.options.king_speed_multiplier.value,
        "civilian_speed_multiplier": world.options.civilian_speed_multiplier.value,
    }

    patch.write_file("options.json", json.dumps(options_dict).encode("utf-8"))