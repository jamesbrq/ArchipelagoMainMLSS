import asyncio
import traceback

import Patch
from CommonClient import ClientCommandProcessor, CommonContext, get_base_parser, gui_enabled, logger, server_loop
import dolphin_memory_engine as dolphin

from NetUtils import NetworkItem, ClientStatus
from worlds.ttyd.Data import location_gsw_info, GSWType
from worlds.ttyd.Items import items_by_id, item_type_dict

RECEIVED_INDEX = 0x803DB860
RECEIVED_ITEM = 0x803DB864
PLAYER_NAME = 0x80003200
GP_BASE = 0x803DAC18
GSWF_BASE = 0x178
GSW0 = 0x174
GSW_BASE = 0x578

def read_string(address: int, length: int):
    return dolphin.read_bytes(address, length).decode().strip("\0")

def get_rom_item_id(item: NetworkItem):
    item = item_type_dict[items_by_id[item.item].itemName]
    return item

def _get_bit_address(bit_number: int) -> tuple:
    word_index = bit_number >> 5
    bit_position = bit_number & 0x1F
    word_address = GP_BASE + (word_index * 4) + GSWF_BASE
    byte_within_word = 3 - (bit_position >> 3)
    byte_address = word_address + byte_within_word
    bit = bit_position & 0x7
    return byte_address, bit

def gswf_set(bit_number: int):
    result = _get_bit_address(bit_number)
    if not result: return False
    byte_address, bit = result
    current_byte = dolphin.read_byte(byte_address)
    bit_mask = 1 << bit
    new_byte = current_byte | bit_mask
    dolphin.write_byte(byte_address, new_byte)
    return result

def gswf_check(bit_number: int) -> bool:
    result = _get_bit_address(bit_number)
    if not result: return False
    byte_address, bit = result
    current_byte = dolphin.read_byte(byte_address)
    bit_mask = 1 << bit
    return bool(current_byte & bit_mask)

def gsw_byte_set(index, value):
    return dolphin.write_word(GP_BASE + GSW0, value) if index == 0 else dolphin.write_byte(GP_BASE + index + GSW_BASE, value)

def gsw_byte_get(index):
    return dolphin.read_word(GP_BASE + GSW0) if index == 0 else dolphin.read_byte(GP_BASE + index + GSW_BASE)


class TTYDCommandProcessor(ClientCommandProcessor):
    def __init__(self, ctx: CommonContext):
        super().__init__(ctx)

    def _cmd_set_gswf(self, bit_number: int):
        byte_address, bit = gswf_set(int(bit_number))
        logger.info(f"Bit {bit} written at {byte_address}")

    def _cmd_check_gswf(self, bit_number: int):
        result = gswf_check(int(bit_number))
        logger.info(f"GSWF Check: {result}")


class TTYDContext(CommonContext):
    command_processor = TTYDCommandProcessor
    game = "Paper Mario The Thousand Year Door"
    items_handling = 0b101
    dolphin_connected: bool = False
    slot_data: dict = {}
    checked_locations = set()

    def __init__(self, server_address, password):
        super().__init__(server_address, password)

    async def server_auth(self, password_requested: bool = False):
        if password_requested and not self.password:
            await super(TTYDContext, self).server_auth(password_requested)
        await self.send_connect()

    def on_package(self, cmd: str, args: dict):
        if cmd in {"Connected"}:
            self.slot = args["slot"]
            self.slot_data = args["slot_data"]
        elif cmd == "Retrieved":
            if "keys" not in args:
                logger.warning(f"invalid Retrieved packet to TTYDClient: {args}")
                return

    def run_gui(self):
        from kvui import GameManager

        class TTYDManager(GameManager):
            logging_pairs = [("Client", "Archipelago")]
            base_title = "Archipelago TTYD Client"

        self.ui = TTYDManager(self)
        self.ui_task = asyncio.create_task(self.ui.async_run(), name="UI")

    async def receive_items(self):
        index = dolphin.read_word(RECEIVED_INDEX)
        for i in range(index, len(self.items_received)):
            dolphin.write_word(RECEIVED_ITEM, get_rom_item_id(self.items_received[i]))
            await asyncio.sleep(0.05)
            dolphin.write_word(RECEIVED_INDEX, i + 1)

    async def check_ttyd_locations(self):
        locations_to_send = set()
        try:
            for location, gsw_info in location_gsw_info.items():
                gsw_type, offset, value = gsw_info
                if gsw_type.value == 0:
                    if gsw_byte_get(offset) >= value:
                        locations_to_send.add(location)
                elif gsw_type.value == 1:
                    if gswf_check(offset):
                        locations_to_send.add(location)
            if len(locations_to_send) > 0:
                self.checked_locations &= locations_to_send
                await self.send_msgs([{"cmd": 'LocationChecks', "locations": locations_to_send}])
        except Exception as e:
            logger.error(traceback.format_exc())

    def save_loaded(self) -> bool:
        value = gsw_byte_get(1700)
        return value > 0


async def _patch_game(patch_file: str):
    metadata, output_file = Patch.create_rom_file(patch_file)


# Sends player items from server
# Checks for player status to see if they are in/loading a level
# Checks location status inside of levels
async def ttyd_sync_task(ctx: TTYDContext):
    logger.info("Starting Dolphin connector...")
    while not ctx.exit_event.is_set():
        if dolphin.is_hooked() and ctx.dolphin_connected:
            if ctx.slot:
                if not ctx.save_loaded():
                    await asyncio.sleep(0.1)
                    continue
                await ctx.receive_items()
                await ctx.check_ttyd_locations()
                if not ctx.finished_game and gsw_byte_get(1708) >= 18:
                    await ctx.send_msgs([{"cmd": "StatusUpdate", "status": ClientStatus.CLIENT_GOAL}])
                await asyncio.sleep(0.1)
            else:
                if not ctx.auth:
                    ctx.auth = read_string(PLAYER_NAME, 0x10).strip()
                    if not ctx.auth:
                        ctx.auth = None
                        logger.info("No slot name was detected. Please load the correct ROM.")
                        ctx.dolphin_connected = False
                        dolphin.un_hook()
                        await asyncio.sleep(3)
                        continue
                await ctx.server_auth()
                await asyncio.sleep(0.1)
        else:
            try:
                logger.info("Attempting to connect to Dolphin...")
                dolphin.hook()
                if not dolphin.is_hooked():
                    logger.info("Connection to Dolphin failed... Attempting again")
                    ctx.dolphin_connected = False
                    await ctx.disconnect()
                    await asyncio.sleep(3)
                    continue

                logger.info("Dolphin connected")
                ctx.dolphin_connected = True
            except Exception as e:
                dolphin.un_hook()
                logger.info("Connection to Dolphin failed... Attempting again")
                logger.error(traceback.format_exc())
                ctx.dolphin_connected = False
                await ctx.disconnect()
                await asyncio.sleep(3)
                continue


def launch(*args):
    async def main(args):
        if args.patch_file:
            await asyncio.create_task(_patch_game(args.patch_file))
        ctx = TTYDContext(args.connect, args.password)
        ctx.server_task = asyncio.create_task(server_loop(ctx), name="ServerLoop")
        if gui_enabled:
            ctx.run_gui()
        ctx.run_cli()
        ctx.gl_sync_task = asyncio.create_task(ttyd_sync_task(ctx), name="Gauntlet Legends Sync Task")

        await ctx.exit_event.wait()
        ctx.server_address = None

        await ctx.shutdown()

    parser = get_base_parser()
    parser.add_argument("patch_file", default="", type=str, nargs="?", help="Path to an APTTYD file")
    args = parser.parse_args(args)

    import colorama

    colorama.just_fix_windows_console()
    asyncio.run(main(args))
    colorama.deinit()
