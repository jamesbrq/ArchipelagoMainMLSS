import io
import json

from gclib.gcm import GCM
from gclib.dol import DOL
from typing import TYPE_CHECKING, Dict, Tuple, Iterable
from BaseClasses import Location, ItemClassification
from settings import get_settings
from worlds.Files import APProcedurePatch, APTokenMixin, APPatchExtension, AutoPatchExtensionRegister
from .Items import items_by_id, ItemData
from .Locations import locationName_to_data
from .Data import Rels

if TYPE_CHECKING:
    from . import TTYDWorld


def get_base_rom_as_bytes() -> bytes:
    with open(get_settings().ttyd_options.rom_file, "rb") as infile:
        base_rom_bytes = bytes(infile.read())
    return base_rom_bytes

class TTYDPatchExtension(APPatchExtension):
    game = "Paper Mario The Thousand Year Door"

    @staticmethod
    def patch_items(caller: "TTYDProcedurePatch") -> None:
        from CommonClient import logger
        locations: Dict[str, Tuple] = json.loads(caller.get_file(f"locations.json").decode("utf-8"))
        logger.info(f"PATCHING")
        rels: Dict[Rels, io.BytesIO] = {}
        dol = DOL()
        dol.read(caller.iso.read_file_data("sys/main.dol"))
        for rel in Rels:
            if rel == Rels.dol:
                continue
            path = get_rel_path(rel)
            rels[rel] = caller.iso.read_file_data(path)
        for location_name, (item_id, player) in locations.items():
            data = locationName_to_data.get(location_name, None)
            if data is None:
                continue
            if data.offset != 0:
                item_data = items_by_id.get(item_id, ItemData(code=0, itemName="", progression=ItemClassification.filler, rom_id=0x86))
                if data.rel == Rels.dol:
                    logger.info(f"PATCHING {location_name} with {item_data.itemName}")
                    dol.data.seek(data.offset)
                    dol.data.write(item_data.rom_id.to_bytes(4, "big"))
                else:
                    print("pog")
                    #rels[data.rel].seek(data.offset)
                    #rels[data.rel].write(item_data.rom_id.to_bytes(4, "big"))
        for rel in rels.keys():
            caller.iso.changed_files[get_rel_path(rel)] = rels[rel]
        caller.iso.changed_files["sys/main.dol"] = dol.data
        for _,_ in caller.iso.export_disc_to_iso_with_changed_files(caller.file_path + ".iso"):
            continue

def get_rel_path(rel: Rels):
    return f'files/rel/{rel.value}.rel'


class TTYDProcedurePatch(APProcedurePatch, APTokenMixin):
    game = "Paper Mario The Thousand Year Door"
    hash = "4b1a5897d89d9e74ec7f630eefdfd435"
    patch_file_ending = ".apttyd"
    result_file_ending = ".iso"
    file_path: str = ""
    iso: GCM

    procedure = [
        ("patch_items", [])
    ]

    @classmethod
    def get_source_data(cls) -> bytes:
        return get_base_rom_as_bytes()

    def patch(self, target) -> None:
        self.iso = GCM(get_settings().ttyd_options.rom_file)
        self.iso.read_entire_disc()
        self.file_path = target
        self.read()
        patch_extender = AutoPatchExtensionRegister.get_handler(self.game)
        assert not isinstance(self.procedure, str), f"{type(self)} must define procedures"
        for step, args in self.procedure:
            if isinstance(patch_extender, list):
                extension = next((item for item in [getattr(extender, step, None) for extender in patch_extender]
                                  if item is not None), None)
            else:
                extension = getattr(patch_extender, step, None)
            if extension is not None:
                extension(self, *args)

def write_files(world: "TTYDWorld", patch: TTYDProcedurePatch) -> None:
    options_dict = {
        "seed": world.multiworld.seed,
        "player": world.player,
    }
    patch.write_file("options.json", json.dumps(options_dict).encode("UTF-8"))
    patch.write_file(f"locations.json", json.dumps(locations_to_dict(world.multiworld.get_locations(world.player))).encode("UTF-8"))

def locations_to_dict(locations: Iterable[Location]) -> Dict[str, Tuple]:
    return {location.name: (location.item.code, location.item.player) if location.item is not None else (0, 0)
                    for location in locations}