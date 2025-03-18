import asyncio

import Patch
import Utils
from CommonClient import ClientCommandProcessor, CommonContext, get_base_parser, gui_enabled, logger, server_loop


class TTYDCommandProcessor(ClientCommandProcessor):
    def __init__(self, ctx: CommonContext):
        super().__init__(ctx)


class TTYDContext(CommonContext):
    command_processor = TTYDCommandProcessor
    game = "Paper Mario The Thousand Year Door"
    items_handling = 0b101

    def __init__(self, server_address, password):
        super().__init__(server_address, password)

    async def server_auth(self, password_requested: bool = False):
        if password_requested and not self.password:
            await super(TTYDContext, self).server_auth(password_requested)
        await self.get_username()
        await self.send_connect()

    def on_package(self, cmd: str, args: dict):
        if cmd in {"Connected"}:
            self.slot = args["slot"]
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


async def _patch_game(patch_file: str):
    metadata, output_file = Patch.create_rom_file(patch_file)


# Sends player items from server
# Checks for player status to see if they are in/loading a level
# Checks location status inside of levels
async def ttyd_sync_task(ctx: TTYDContext):
    await asyncio.sleep(1)


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
