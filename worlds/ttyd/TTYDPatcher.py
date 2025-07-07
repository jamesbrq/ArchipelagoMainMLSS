import io

from typing import Dict
from settings import get_settings
from worlds.ttyd.Data import Rels


class TTYDPatcher:
    rels: Dict[Rels, io.BytesIO] = {}

    def __init__(self):
        from gclib.gcm import GCM
        from gclib.dol import DOL

        self.iso = GCM(get_settings().ttyd_options.rom_file)
        self.iso.read_entire_disc()
        self.dol = DOL()
        self.dol.read(self.iso.read_file_data("sys/main.dol"))
        for rel in Rels:
            if rel == Rels.dol:
                continue
            path = get_rel_path(rel)
            self.rels[rel] = self.iso.read_file_data(path)

def get_rel_path(rel: Rels):
    return f'files/rel/{rel.value}.rel'
