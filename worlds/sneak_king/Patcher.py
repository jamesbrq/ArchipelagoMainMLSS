import json
import os
import pkgutil
import shutil
import struct
import tempfile

from typing import TYPE_CHECKING

from settings import get_settings
from worlds.Files import APProcedurePatch

from .xdvdfs import XDVDFSImage, create_xiso
import subprocess

if TYPE_CHECKING:
    from . import SneakKingWorld


XBE_MAGIC = b"XBEH"

XBE_SECTIONS = [
    # (va_start, file_offset, size)
    (0x00011000, 0x00001000, 0x1DB5BC),  # .text
    (0x002AFB20, 0x0029B000, 0x01FF2C),  # .rdata
    (0x002CFA60, 0x002BB000, 0x013260),  # .data
]


def va_to_file_offset(va: int) -> int:
    for sec_va, sec_file, sec_size in XBE_SECTIONS:
        if sec_va <= va < sec_va + sec_size:
            return va - sec_va + sec_file
    return va - 0x10000


def _apply_xbe_patches(xbe_data: bytearray, patches: dict, seed_options: dict) -> None:
    for patch in patches["patches"]["required"]:
        new = bytes.fromhex(patch["new"])
        offset = va_to_file_offset(int(patch["va"], 16))
        xbe_data[offset:offset + len(new)] = new

    for patch in patches["patches"].get("settings", []):
        offset = va_to_file_offset(int(patch["va"], 16))
        option_key = patch["option"]
        mode = patch.get("mode", "set")

        if mode == "multiply":
            value = patch["base"] * seed_options.get(option_key, 1.0)
        elif mode == "divide":
            divisor = seed_options.get(option_key, 1.0)
            value = patch["base"] / divisor if divisor != 0 else patch["base"]
        elif mode == "map":
            mapping = patches.get(patch["map_name"], {})
            value = mapping.get(str(seed_options.get(option_key, 0)), 0)
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


def _apply_fetm_patches(fetm_data: bytearray, patches: dict, seed_options: dict) -> None:
    for patch in patches["patches"].get("fetm_settings", []):
        offset = int(patch["offset"], 16)
        option_key = patch["option"]
        mode = patch.get("mode", "set")

        if mode == "multiply":
            value = patch["base"] * seed_options.get(option_key, 1.0)
        elif mode == "divide":
            divisor = seed_options.get(option_key, 1.0)
            value = patch["base"] / divisor if divisor != 0 else patch["base"]
        else:
            value = seed_options.get(option_key, patch.get("default", 0))

        if patch["type"] == "float":
            fetm_data[offset:offset + 4] = struct.pack("<f", value)
        elif patch["type"] == "byte":
            fetm_data[offset] = int(value) & 0xFF
        elif patch["type"] == "dword":
            fetm_data[offset:offset + 4] = struct.pack("<I", int(value) & 0xFFFFFFFF)


class SneakKingProcedurePatch(APProcedurePatch):
    game = "Sneak King"
    patch_file_ending = ".apsk"
    result_file_ending = ".iso"
    hash = ''
    procedure = []

    @classmethod
    def get_source_data(cls) -> bytes:
        raise NotImplementedError

    def patch(self, target: str) -> None:
        self.read()

        patch_data = pkgutil.get_data(__name__, "json/patches.json")
        if patch_data is None:
            raise FileNotFoundError("Missing patches.json in APWorld")
        patches = json.loads(patch_data.decode("utf-8"))
        xbe_path = patches["xbe_file"]
        fetm_path = patches.get("fetm_file", "")

        seed_options = json.loads(self.get_file("options.json").decode("utf-8"))
        source = str(get_settings().sneak_king_options.rom_file)

        tmpdir = tempfile.mkdtemp()
        try:
            # Extract all files from the source ISO to disk — nothing held in memory
            with XDVDFSImage(source) as iso:
                iso.extract_all(tmpdir)

            # Patch just the XBE on disk
            xbe_file = os.path.join(tmpdir, xbe_path.replace("/", os.sep))
            with open(xbe_file, "rb") as f:
                xbe_data = bytearray(f.read())

            if xbe_data[:4] != XBE_MAGIC:
                raise ValueError("Invalid XBE: missing XBEH magic")

            _apply_xbe_patches(xbe_data, patches, seed_options)

            with open(xbe_file, "wb") as f:
                f.write(xbe_data)

            # Patch the FETM on disk (civilian speeds, etc.)
            if fetm_path and patches["patches"].get("fetm_settings"):
                fetm_file = os.path.join(tmpdir, fetm_path.replace("/", os.sep))
                with open(fetm_file, "rb") as f:
                    fetm_data = bytearray(f.read())

                _apply_fetm_patches(fetm_data, patches, seed_options)

                with open(fetm_file, "wb") as f:
                    f.write(fetm_data)

            create_xiso(tmpdir, target)
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)


def write_files(world: "SneakKingWorld", patch: SneakKingProcedurePatch) -> None:
    options_dict = {
        "seed": world.multiworld.seed,
        "seed_name": world.multiworld.seed_name,
        "player": world.player,
        "player_name": world.multiworld.player_name[world.player],
        "starting_level": world.options.starting_level.value,
        "king_speed_multiplier": world.options.king_speed_multiplier.value,
        "civilian_speed_multiplier": world.options.civilian_speed_multiplier.value,
    }

    patch.write_file("options.json", json.dumps(options_dict).encode("utf-8"))
