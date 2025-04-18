import io
import json
import pkgutil
import bsdiff4

from gclib.gcm import GCM
from gclib.dol import DOL
from typing import TYPE_CHECKING, Dict, Tuple, Iterable
from BaseClasses import Location, ItemClassification
from settings import get_settings
from worlds.Files import APProcedurePatch, APTokenMixin, APPatchExtension, AutoPatchExtensionRegister
from .Items import items_by_id, ItemData, item_type_dict
from .Locations import locationName_to_data
from .Data import Rels, shop_items, tubu_dt, item_prices, rel_filepaths

if TYPE_CHECKING:
    from . import TTYDWorld

class TTYDPatchExtension(APPatchExtension):
    game = "Paper Mario The Thousand Year Door"

    @staticmethod
    def patch_mod(caller: "TTYDProcedurePatch") -> None:
        seed_options = json.loads(caller.get_file("options.json").decode("utf-8"))
        caller.dol.data.seek(0x200)
        caller.dol.data.write(seed_options["player_name"].encode("utf-8")[0:16])
        caller.dol.data.seek(0x210)
        caller.dol.data.write(seed_options["seed"].encode("utf-8")[0:16])
        caller.dol.data.seek(0x220)
        caller.dol.data.write(seed_options["chapter_clears"].to_bytes(1, "big"))
        caller.dol.data.seek(0x221)
        caller.dol.data.write(seed_options["starting_partner"].to_bytes(1, "big"))
        caller.dol.data.seek(0x222)
        caller.dol.data.write(seed_options["yoshi_color"].to_bytes(1, "big"))
        caller.dol.data.seek(0x223)
        caller.dol.data.write((1).to_bytes(1, "big"))
        caller.dol.data.seek(0x224)
        caller.dol.data.write((0x80003230).to_bytes(4, "big"))
        caller.dol.data.seek(0x230)
        caller.dol.data.write(seed_options["yoshi_name"].encode("utf-8")[0:8] + b"\x00")
        caller.dol.data.seek(0xEB6B6)
        caller.dol.data.write(int.to_bytes(seed_options["starting_coins"], 2, "big"))
        caller.dol.data.seek(0x1888)
        caller.dol.data.write(pkgutil.get_data(__name__, "data/US.bin"))
        caller.dol.data.seek(0x6CE38)
        caller.dol.data.write(int.to_bytes(0x4BF94A50, 4, "big"))
        #for key, value in tubu_dt.items():
            #caller.dol.data.seek(key)
            #caller.dol.data.write(value.to_bytes(2, "big"))
        caller.iso.add_new_directory("files/mod")
        caller.iso.add_new_directory("files/mod/subrels")
        for file in [file for file in rel_filepaths if file != "mod"]:
            caller.iso.add_new_file(f"files/mod/subrels/{file}.rel", io.BytesIO(pkgutil.get_data(__name__, f"data/{file}.rel")))
        caller.iso.add_new_file("files/mod/mod.rel", io.BytesIO(pkgutil.get_data(__name__, f"data/mod.rel")))



    @staticmethod
    def close_iso(caller: "TTYDProcedurePatch") -> None:
        for rel in caller.rels.keys():
            caller.iso.changed_files[get_rel_path(rel)] = caller.rels[rel]
        caller.iso.changed_files["sys/main.dol"] = caller.dol.data
        for _,_ in caller.iso.export_disc_to_iso_with_changed_files(caller.file_path):
            continue

    @staticmethod
    def patch_icon(caller: "TTYDProcedurePatch") -> None:
        icon_patch = pkgutil.get_data(__name__, f"data/icon.bsdiff4")
        bin_patch = pkgutil.get_data(__name__, f"data/icon_bin.bsdiff4")
        icon_file = caller.iso.read_file_data("files/icon.tpl")
        bin_file = caller.iso.read_file_data("files/icon.bin")
        icon_file.seek(0)
        original_icon_data = icon_file.read()
        bin_file.seek(0)
        original_bin_data = bin_file.read()
        patched_icon_data = bsdiff4.patch(original_icon_data, icon_patch)
        patched_bin_data = bsdiff4.patch(original_bin_data, bin_patch)
        new_icon_file = io.BytesIO(patched_icon_data)
        new_bin_file = io.BytesIO(patched_bin_data)
        caller.iso.changed_files["files/icon.tpl"] = new_icon_file
        caller.iso.changed_files["files/icon.bin"] = new_bin_file


    @staticmethod
    def patch_items(caller: "TTYDProcedurePatch") -> None:
        from CommonClient import logger
        locations: Dict[str, Tuple] = json.loads(caller.get_file(f"locations.json").decode("utf-8"))
        for location_name, (item_id, player) in locations.items():
            data = locationName_to_data.get(location_name, None)
            if data is None:
                continue
            if data.offset:
                if player != caller.player:
                    item_data = ItemData(code=0, itemName="", progression=ItemClassification.filler, rom_id=0x71)
                else:
                    item_data = items_by_id.get(item_id, ItemData(code=0, itemName="", progression=ItemClassification.filler, rom_id=0x0))
                if item_data.rom_id != 0x71:
                    item_data.rom_id = item_type_dict.get(item_data.itemName, 0x0)
                    if item_data.rom_id == 0:
                        logger.error(f"Item {item_data.itemName} not found in item_type_dict")
                if data.rel == Rels.dol:
                    continue
                    #for offset in data.offset:
                        #dol.data.seek(offset)
                        #dol.data.write(item_data.rom_id.to_bytes(4, "big"))
                else:
                    for i, offset in enumerate(data.offset):
                        if "30 Coins" in data.name and i == 1:
                            caller.rels[Rels.pik].seek(offset)
                            caller.rels[Rels.pik].write(item_data.rom_id.to_bytes(4, "big"))
                            continue
                        caller.rels[data.rel].seek(offset)
                        caller.rels[data.rel].write(item_data.rom_id.to_bytes(4, "big"))
                        if data.id in shop_items:
                            caller.rels[data.rel].seek(offset + 4)
                            if item_data.rom_id == 0x71:
                                caller.rels[data.rel].write(int.to_bytes(20, 4, "big"))
                            else:
                                caller.rels[data.rel].write(int.to_bytes(item_prices.get(item_data.code, 10), 4, "big"))
        for rel in caller.rels.keys():
            caller.iso.changed_files[get_rel_path(rel)] = caller.rels[rel]
        caller.iso.changed_files["sys/main.dol"] = caller.dol.data
        for _,_ in caller.iso.export_disc_to_iso_with_changed_files(caller.file_path):
            continue

def get_rel_path(rel: Rels):
    return f'files/rel/{rel.value}.rel'


class TTYDProcedurePatch(APProcedurePatch, APTokenMixin):
    game = "Paper Mario The Thousand Year Door"
    hash = "4b1a5897d89d9e74ec7f630eefdfd435"
    patch_file_ending = ".apttyd"
    result_file_ending = ".iso"
    file_path: str = ""
    rels: Dict[Rels, io.BytesIO] = {}
    iso: GCM
    dol: DOL

    procedure = [
        ("patch_mod", []),
        ("patch_icon", []),
        ("patch_items", []),
        ("close_iso", [])
    ]

    def patch(self, target) -> None:
        self.iso = GCM(get_settings().ttyd_options.rom_file)
        self.iso.read_entire_disc()
        self.dol = DOL()
        self.dol.read(self.iso.read_file_data("sys/main.dol"))
        for rel in Rels:
            if rel == Rels.dol:
                continue
            path = get_rel_path(rel)
            self.rels[rel] = self.iso.read_file_data(path)
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
        "seed": world.multiworld.seed_name,
        "player": world.player,
        "player_name": world.multiworld.player_name[world.player],
        "yoshi_name": world.options.yoshi_name.value,
        "yoshi_color": world.options.yoshi_color.value,
        "starting_partner": world.options.starting_partner.value,
        "chapter_clears": world.options.chapter_clears.value,
        "starting_coins": world.options.starting_coins.value,
    }
    patch.write_file("options.json", json.dumps(options_dict).encode("UTF-8"))
    patch.write_file(f"locations.json", json.dumps(locations_to_dict(world.multiworld.get_locations(world.player))).encode("UTF-8"))

def locations_to_dict(locations: Iterable[Location]) -> Dict[str, Tuple]:
    return {location.name: (location.item.code, location.item.player) if location.item is not None else (0, 0)
                    for location in locations}