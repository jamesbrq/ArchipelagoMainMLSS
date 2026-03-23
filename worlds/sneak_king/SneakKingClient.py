import asyncio
import subprocess
import typing

import Patch
import Utils
import kvui
import settings
from CommonClient import ClientCommandProcessor, get_base_parser, gui_enabled, logger, server_loop
from NetUtils import ClientStatus

tracker_loaded = False
try:
    from worlds.tracker.TrackerClient import TrackerGameContext as cmmCtx, UT_VERSION
    tracker_loaded = True
except ModuleNotFoundError:
    from CommonClient import CommonContext as cmmCtx
    tracker_loaded = False


def _check_universal_tracker_version() -> bool:
    import re
    if tracker_loaded:
        match = re.search(r"v\d+.(\d+).(\d+)", UT_VERSION)
        if len(match.groups()) < 2:
            return False
        if int(match.groups()[0]) < 2:
            return False
        if int(match.groups()[1]) < 12:
            return False
        return True
    return False


class SneakKingCommandProcessor(ClientCommandProcessor):
    def __init__(self, ctx: cmmCtx):
        super().__init__(ctx)


class SneakKingContext(cmmCtx):
    command_processor = SneakKingCommandProcessor
    game = "Sneak King"
    tags = {"AP"}
    connected: bool = False
    slot_data: dict | None = {}
    checked_locations: set = set()

    def __init__(self, server_address, password):
        super().__init__(server_address, password)
        self.items_handling = 0b111

    async def server_auth(self, password_requested: bool = False):
        if password_requested and not self.password:
            await super(SneakKingContext, self).server_auth(password_requested)
        await self.get_username()
        await self.send_connect()

    def on_package(self, cmd: str, args: dict):
        super().on_package(cmd, args)
        if cmd in {"Connected"}:
            self.slot = args["slot"]
            self.slot_data = args["slot_data"]
            self.team = args["team"]
            if "death_link" in args["slot_data"]:
                Utils.async_start(self.update_death_link(bool(args["slot_data"]["death_link"])))
        elif cmd == "RoomInfo":
            self.seed_name = args["seed_name"]

    def on_deathlink(self, data: typing.Dict[str, typing.Any]) -> None:
        super().on_deathlink(data)
        # TODO: Send death to game

    async def disconnect(self, allow_autoreconnect: bool = False):
        await super().disconnect()
        self.slot = None
        self.slot_data = None
        self.team = None
        self.checked_locations = set()
        self.seed_name = None
        self.connected = False

    def make_gui(self) -> "type[kvui.GameManager]":
        from kvui import GameManager
        class SneakKingManager(GameManager):
            logging_pairs = [("Client", "Archipelago")]
            base_title = "Archipelago Sneak King Client"
        if not _check_universal_tracker_version():
            return SneakKingManager
        class TrackerManager(super().make_gui()):
            logging_pairs = [("Client", "Archipelago")]
            base_title = f"Archipelago Sneak King Client with {UT_VERSION}"
        return TrackerManager

    async def receive_items(self):
        # TODO: Send items to game
        pass

    async def check_locations(self):
        # TODO: Check game memory for completed locations
        pass

    async def check_goal(self):
        # TODO: Check if goal condition is met
        pass


async def sneak_king_sync_task(ctx: SneakKingContext):
    logger.info("Starting Sneak King connector...")
    while not ctx.exit_event.is_set():
        if ctx.connected:
            if ctx.slot:
                try:
                    # TODO: Validate game connection
                    await ctx.receive_items()
                    await ctx.check_locations()
                    await ctx.check_goal()
                    await asyncio.sleep(0.5)
                except Exception:
                    import traceback
                    logger.info(traceback.format_exc())
                    ctx.connected = False
                    await asyncio.sleep(1)
            else:
                await asyncio.sleep(1)
        else:
            # TODO: Attempt connection to game
            await asyncio.sleep(3)


async def _run_game(rom: str):
    import os
    auto_start = settings.get_settings().sneak_king_options.rom_start

    if auto_start is True:
        xemu_path = settings.get_settings().sneak_king_options.xemu_path
        subprocess.Popen(
            [
                xemu_path,
                "-dvd_path",
                os.path.realpath(rom),
            ],
            cwd=Utils.local_path("."),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


async def _patch_and_run_game(patch_file: str):
    metadata, output_file = Patch.create_rom_file(patch_file)
    Utils.async_start(_run_game(output_file))
    return metadata


def launch(*args):
    async def main(args):
        if args.patch_file:
            await asyncio.create_task(_patch_and_run_game(args.patch_file))
        ctx = SneakKingContext(args.connect, args.password)
        ctx.server_task = asyncio.create_task(server_loop(ctx), name="ServerLoop")
        if gui_enabled:
            if tracker_loaded:
                ctx.run_generator()
            ctx.run_gui()
        ctx.run_cli()
        ctx.sync_task = asyncio.create_task(sneak_king_sync_task(ctx), name="Sneak King Sync Task")

        await ctx.exit_event.wait()
        ctx.server_address = None

        await ctx.shutdown()

    parser = get_base_parser()
    parser.add_argument("patch_file", default="", type=str, nargs="?", help="Path to an APSK file")
    args = parser.parse_args(args)

    import colorama

    colorama.just_fix_windows_console()
    asyncio.run(main(args))
    colorama.deinit()
