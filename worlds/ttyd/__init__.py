import logging
import os

from Fill import fill_restrictive
from typing import List, Dict, ClassVar, Any, Set
from settings import UserFilePath, Group
from BaseClasses import Tutorial, ItemClassification, CollectionState, Item, Location
from worlds.AutoWorld import WebWorld, World
from .Data import starting_partners, limit_eight, stars, chapter_items, limited_location_ids, limit_pit, \
    pit_exclusive_tattle_stars_required, dazzle_counts, dazzle_location_names, star_locations, chapter_keysanity_tags, \
    chapter_keys
from .Locations import all_locations, location_table, location_id_to_name, TTYDLocation, locationName_to_data, \
    get_locations_by_tags, get_vanilla_item_names, get_location_names, LocationData
from .Options import Piecesanity, TTYDOptions, YoshiColor, StartingPartner, PitItems, LimitChapterEight, Goal, \
    DazzleRewards, StarShuffle
from .Items import TTYDItem, itemList, item_table, ItemData, items_by_id
from .Regions import create_regions, connect_regions, get_regions_dict, register_indirect_connections
from .Rom import TTYDProcedurePatch, write_files
from .Rules import set_rules, get_tattle_rules_dict, set_tattle_rules
from worlds.LauncherComponents import Component, SuffixIdentifier, Type, components, launch_subprocess


def launch_client(*args):
    from .TTYDClient import launch
    launch_subprocess(launch, name="TTYDClient", args=args)


components.append(
    Component(
        "TTYDClient",
        func=launch_client,
        component_type=Type.CLIENT,
        file_identifier=SuffixIdentifier(".apttyd"),
    ),
)


class TTYDWebWorld(WebWorld):
    theme = 'partyTime'
    bug_report_page = "https://github.com/jamesbrq/ArchipelagoTTYD/issues"
    tutorials = [
        Tutorial(
            tutorial_name='Setup Guide',
            description='A guide to setting up Paper Mario: The Thousand-Year Door for Archipelago.',
            language='English',
            file_name='setup_en.md',
            link='setup/en',
            authors=['jamesbrq']
        )
    ]


class TTYDSettings(Group):
    class DolphinPath(UserFilePath):
        """
        The location of the Dolphin you want to auto launch patched ROMs with
        """
        is_exe = True
        description = "Dolphin Executable"

    class RomFile(UserFilePath):
        """File name of the TTYD US iso"""
        copy_to = "Paper Mario - The Thousand-Year Door (USA).iso"
        description = "US TTYD .iso File"

    dolphin_path: DolphinPath = DolphinPath(None)
    rom_file: RomFile = RomFile(RomFile.copy_to)
    rom_start: bool = True


class TTYDWorld(World):
    """
    Paper Mario: The Thousand-Year Door is a quirky, turn-based RPG with a paper-craft twist.
    Mario teams up with oddball allies to stop an ancient evil sealed behind a magical door.
    Set in Rogueport, the game mixes platforming, puzzles, and witty, self-aware dialogue.
    Battles play out on a stage with timed button presses and a live audience cheering you on.
    """
    game = "Paper Mario: The Thousand-Year Door"
    web = TTYDWebWorld()

    options_dataclass = TTYDOptions
    options: TTYDOptions
    settings: ClassVar[TTYDSettings]
    item_name_to_id = {name: data.id for name, data in item_table.items()}
    location_name_to_id = {loc_data.name: loc_data.id for loc_data in all_locations}
    required_client_version = (0, 6, 2)
    disabled_locations: set
    excluded_regions: set
    required_chapters: List[int]
    limited_chapters: List[int]
    limited_chapter_locations: List[Set[Location]]
    limited_misc_locations: Set[Location]
    limited_misc_items: List[TTYDItem]
    limited_item_names: List[Set[str]]
    limited_items: List[List[TTYDItem]]
    limited_state: CollectionState = None
    locked_item_frequencies: Dict[str, int]
    ut_can_gen_without_yaml = True
    keysanity_locations: List[List[Location]]
    keysanity_items: List[List[TTYDItem]]

    def generate_early(self) -> None:
        self.disabled_locations = set()
        self.excluded_regions = set()
        self.required_chapters = []
        self.limited_chapters = []
        self.limited_chapter_locations = [set() for _ in range(8)]
        self.limited_misc_locations = set()
        self.limited_item_names = [set() for _ in range(8)]
        self.limited_items = []
        self.limited_misc_items = []
        self.locked_item_frequencies = {}
        self.keysanity_locations = []
        self.keysanity_items = [[] for _ in range(8)]
        # implementing yaml-less UT support
        if hasattr(self.multiworld, "re_gen_passthrough"):
            if self.game in self.multiworld.re_gen_passthrough:
                slot_data = self.multiworld.re_gen_passthrough[self.game]
                self.options.goal.value = slot_data["goal"]
                self.options.goal_stars.value = slot_data["goal_stars"]
                self.options.palace_stars.value = slot_data["palace_stars"]
                self.options.pit_items.value = slot_data["pit_items"]
                self.options.limit_chapter_logic.value = slot_data["limit_chapter_logic"]
                self.options.limit_chapter_eight.value = slot_data["limit_chapter_eight"]
                self.options.palace_skip.value = slot_data["palace_skip"]
                self.options.open_westside.value = slot_data["westside"]
                self.options.tattlesanity.value = slot_data["tattlesanity"]
                self.options.disable_intermissions.value = slot_data["disable_intermissions"]
                return
        if self.options.limit_chapter_eight and self.options.palace_skip:
            logging.warning(f"{self.player_name}'s has enabled both Palace Skip and Limit Chapter 8. "
                            f"Disabling the Limit Chapter 8 option due to incompatibility.")
            self.options.limit_chapter_eight.value = LimitChapterEight.option_false
        if self.options.goal == Goal.option_bonetail and self.options.goal_stars < 5:
            logging.warning(f"{self.player_name}'s has Bonetail as the goal with less than 5 stars required. "
                            f"Increasing number of goal stars to 5 for accessibility.")
            self.options.goal_stars.value = 5
        if self.options.palace_stars > self.options.goal_stars:
            logging.warning(f"{self.player_name}'s has more palace stars required than goal stars. "
                            f"Reducing number of stars required to enter the palace of shadow for accessibility.")
            self.options.palace_stars.value = self.options.goal_stars.value
        chapters = [i for i in range(1, 8)]
        for i in range(self.options.goal_stars.value):
            self.required_chapters.append(chapters.pop(self.multiworld.random.randint(0, len(chapters) - 1)))
        if self.options.limit_chapter_logic:
            self.limited_chapters += chapters
        if self.options.limit_chapter_eight:
            self.limited_chapters += [8]
        if self.options.palace_skip:
            self.excluded_regions.update(["Palace of Shadow", "Palace of Shadow (Post-Riddle Tower)"])
        if not self.options.tattlesanity:
            self.excluded_regions.update(["Tattlesanity"])
        if self.options.goal != Goal.option_shadow_queen:
            self.excluded_regions.update(["Shadow Queen"])
            if self.options.tattlesanity:
                self.disabled_locations.update(["Tattle: Shadow Queen"])
        if self.options.tattlesanity and self.options.disable_intermissions:
            self.disabled_locations.update(["Tattle: Lord Crump"])
        if self.options.tattlesanity:
            extra_disabled = [location.name for name, locations in get_regions_dict().items()
                if name in self.excluded_regions for location in locations]
            for location_name, locations in get_tattle_rules_dict().items():
                if len(locations) == 0:
                    if "Palace of Shadow (Post-Riddle Tower)" in self.excluded_regions:
                        self.disabled_locations.update([location_name])
                else:
                    if all([location_id_to_name[location] in self.disabled_locations or location_id_to_name[location] in extra_disabled for location in locations]):
                        self.disabled_locations.update([location_name])

    def create_regions(self) -> None:
        create_regions(self)
        connect_regions(self)
        register_indirect_connections(self)
        if not self.options.keysanity:
            for i, tag in enumerate(chapter_keysanity_tags):
                self.keysanity_locations.append([self.get_location(location) for location in get_location_names(get_locations_by_tags(tag)) if location not in self.disabled_locations])
                if len(self.keysanity_locations[i]) > 0:
                    for item_name, count in chapter_keys[i + 1].items():
                            self.keysanity_items[i].extend([self.create_item(item_name) for _ in range(count)])
                            self.locked_item_frequencies[item_name] = self.locked_item_frequencies.get(item_name, 0) + count
            if self.options.limit_chapter_eight:
                self.keysanity_locations[7] = []
                self.keysanity_items[7] = []
        for chapter in self.limited_chapters:
            self.limited_chapter_locations[chapter - 1].update([self.get_location(location_id_to_name[location]) for location in limited_location_ids[chapter - 1]])
        if self.options.tattlesanity:
            self.limit_tattle_locations()
        self.lock_item_remove_from_pool("Rogueport Center: Goombella", starting_partners[self.options.starting_partner.value - 1])
        if self.options.star_shuffle == StarShuffle.option_vanilla:
            self.lock_vanilla_items_remove_from_pool(get_locations_by_tags("star"))
        elif self.options.star_shuffle == StarShuffle.option_stars_only:
            locations = get_locations_by_tags("star")
            items = [location.vanilla_item for location in locations]
            self.multiworld.random.shuffle(items)
            for i, location in enumerate(locations):
                self.lock_item_remove_from_pool(location.name, items_by_id[items[i]].item_name)
        if self.options.goal == Goal.option_shadow_queen:
            self.lock_item_remove_from_pool("Shadow Queen", "Victory")
        if self.options.limit_chapter_eight:
            for location in [location for location in get_locations_by_tags("chapter_8")]:
                if "Palace Key (Tower)" in location.name:
                    self.lock_item_remove_from_pool(location.name, "Palace Key (Tower)")
                elif "Palace Key" in location.name:
                    self.lock_item_remove_from_pool(location.name, "Palace Key")
            self.lock_item_remove_from_pool("Palace of Shadow Gloomtail Room: Star Key", "Star Key")
        if self.options.palace_skip:
            self.locked_item_frequencies["Palace Key"] = 3
            self.locked_item_frequencies["Palace Key (Tower)"] = 8
            self.locked_item_frequencies["Star Key"] = 1
        if self.options.pit_items == PitItems.option_vanilla:
            self.lock_vanilla_items_remove_from_pool(get_locations_by_tags("pit_floor"))
        if self.options.piecesanity == Piecesanity.option_vanilla:
            self.lock_vanilla_items_remove_from_pool(get_locations_by_tags(["star_piece", "panel"]))
        if self.options.piecesanity == Piecesanity.option_nonpanel_only:
            self.lock_vanilla_items_remove_from_pool(get_locations_by_tags("panel"))
        if not self.options.shinesanity:
            self.lock_vanilla_items_remove_from_pool(get_locations_by_tags("shine"))
        if not self.options.shopsanity:
            self.lock_vanilla_items_remove_from_pool(get_locations_by_tags("shop"))
        if self.options.pit_items == PitItems.option_filler:
            self.lock_filler_items_remove_from_pool(get_locations_by_tags("pit_floor"))
        if self.options.dazzle_rewards == DazzleRewards.option_vanilla:
            self.lock_vanilla_items_remove_from_pool(get_locations_by_tags("dazzle"))
        elif self.options.dazzle_rewards == DazzleRewards.option_filler:
            self.lock_filler_items_remove_from_pool(get_locations_by_tags("dazzle"))


    def limit_tattle_locations(self):
        for stars_required, locations in pit_exclusive_tattle_stars_required.items():
            if stars_required > len(self.required_chapters):
                self.limited_misc_locations.update([self.get_location(location) for location in locations if location not in self.disabled_locations])
        for location_name, locations in get_tattle_rules_dict().items():
            if location_name in self.disabled_locations:
                continue
            if self.options.limit_chapter_eight and len(locations) == 0:
                self.limited_misc_locations.add(self.get_location(location_name))
                continue
            enabled_locations = [location for location in locations if location_id_to_name[location] not in self.disabled_locations]
            if len(enabled_locations) == 0:
                continue
            if self.options.pit_items != PitItems.option_all:
                if all(location in limit_pit for location in enabled_locations):
                    self.limited_misc_locations.add(self.get_location(location_name))
            if self.options.limit_chapter_logic:
                if len(locations) == 1 and locations[0] == 78780511:
                    if 5 in self.limited_chapters:
                        self.limited_misc_locations.add(self.get_location(location_name))
                if all(self.get_location(location_id_to_name[location]) in self.limited_chapter_locations for location in enabled_locations):
                    self.limited_misc_locations.add(self.get_location(location_name))

    def create_items(self) -> None:
        self.limited_items = [[] for _ in range(8)]
        star_pieces = []
        self.limited_state = CollectionState(self.multiworld)
        for chapter in self.limited_chapters:
            logging.info(chapter)
            if chapter != 8:
                self.limited_item_names[chapter - 1].update(chapter_items[chapter] + (
                    [stars[chapter - 1]] if self.options.star_shuffle == StarShuffle.option_all else []))
            else:
                self.limited_item_names[chapter - 1].update(chapter_items[chapter])

        item_names = [item.item_name
                      for item in item_table.values() for _ in
                      range(max(item.frequency - self.locked_item_frequencies.get(item.item_name, 0), 0))]

        logging.info(f"[{self.player}] Initial item_names count: {len(item_names)}")

        for item in self.multiworld.precollected_items[self.player]:
            if item.name in item_names:
                item_names.remove(item.name)

        logging.info(f"[{self.player}] After precollected removal: {len(item_names)}")

        limited_item_index = {
            item_name: index
            for index, item_set in enumerate(self.limited_item_names)
            for item_name in item_set
        }

        logging.info(f"[{self.player}] Limited item names by chapter: {[len(s) for s in self.limited_item_names]}")

        for item_name in list(item_names):
            if item_name in limited_item_index:
                item_names.remove(item_name)
                index = limited_item_index[item_name]
                self.limited_items[index].append(self.create_item(item_name))
            elif item_name == "Star Piece":
                item_names.remove(item_name)
                star_pieces.append(self.create_item(item_name))

        logging.info(f"[{self.player}] After limited/star piece extraction: {len(item_names)} remaining")
        logging.info(f"[{self.player}] Star pieces: {len(star_pieces)}")
        logging.info(f"[{self.player}] Limited items by chapter: {[len(items) for items in self.limited_items]}")

        filler_items = [self.create_item(item_name) for item_name in item_names if
                        item_table[item_name].progression == ItemClassification.filler]
        required_items = [self.create_item(item_name) for item_name in item_names if
                          item_table[item_name].progression != ItemClassification.filler]
        self.random.shuffle(required_items)
        self.random.shuffle(filler_items)

        logging.info(f"[{self.player}] Filler items: {len(filler_items)}, Required items: {len(required_items)}")

        for chapter in self.limited_chapters:
            before_count = len(self.limited_items[chapter - 1])
            self.limited_items[chapter - 1].extend([filler_items.pop() for _ in
                                                    range(len(self.limited_items[chapter - 1]),
                                                          len(self.limited_chapter_locations[chapter - 1]) - len(
                                                              self.keysanity_items[chapter - 1])) if
                                                    len(filler_items) > 0])
            needed = len(self.limited_chapter_locations[chapter - 1]) - len(self.limited_items[chapter - 1]) - len(
                self.keysanity_items[chapter - 1])
            if needed > 0:
                self.limited_items[chapter - 1].extend(
                    [self.create_item(self.get_filler_item_name()) for _ in range(needed)])
            logging.info(
                f"[{self.player}] Chapter {chapter}: locations={len(self.limited_chapter_locations[chapter - 1])}, "
                f"keysanity={len(self.keysanity_items[chapter - 1])}, limited_items={before_count}->{len(self.limited_items[chapter - 1])}, "
                f"needed={needed}, filler_remaining={len(filler_items)}")

        self.limited_misc_items = [self.create_item(self.get_filler_item_name()) for _ in
                                   range(len(self.limited_misc_locations))]

        logging.info(
            f"[{self.player}] Limited misc items: {len(self.limited_misc_items)} for {len(self.limited_misc_locations)} locations")

        _ = {self.random.shuffle(items) for items in self.limited_items}

        dazzle_locations = [self.get_location(location_name) for location_name in dazzle_location_names]
        dazzle_locked_count = 0
        for i, location in enumerate(dazzle_locations):
            if len(star_pieces) < dazzle_counts[i] and location.item is None:
                location.place_locked_item(self.create_filler())
                dazzle_locked_count += 1

        logging.info(f"[{self.player}] Dazzle locations locked with filler: {dazzle_locked_count}")

        _ = {self.limited_state.collect(item, prevent_sweep=True) for item in required_items + star_pieces}

        unfilled_count = len(self.multiworld.get_unfilled_locations(self.player))
        limited_chapter_total = len([location for locations in self.limited_chapter_locations for location in locations if location.item is None])
        limited_chapter_total -= sum(len(self.keysanity_items[chapter - 1]) for chapter in self.limited_chapters)
        filler_count = unfilled_count - len(star_pieces) - len(required_items) - limited_chapter_total - len(
            self.limited_misc_locations) - sum(len(self.keysanity_items[chapter - 1]) for chapter in self.required_chapters)

        logging.info(f"[{self.player}] Filler calculation: unfilled={unfilled_count}, star_pieces={len(star_pieces)}, "
                      f"required={len(required_items)}, limited_chapter_total={limited_chapter_total}, "
                      f"limited_misc={len(self.limited_misc_locations)}, filler_count={filler_count}")
        logging.info(f"[{self.player}] Available filler: {len(filler_items)}, needed: {filler_count}, "
                      f"generating extra: {max(0, filler_count - len(filler_items))}")

        if len(filler_items) < filler_count:
            filler_items += [self.create_item(self.get_filler_item_name()) for _ in
                             range(filler_count - len(filler_items))]

        logging.info(f"[{self.player}] Final itempool additions: star_pieces={len(star_pieces)}, "
                      f"required={len(required_items)}, filler={filler_count}")
        logging.info(f"Before: {len(self.multiworld.itempool)}")
        self.multiworld.itempool += star_pieces
        self.multiworld.itempool += required_items
        self.multiworld.itempool += filler_items[:filler_count]
        logging.info(len(self.multiworld.itempool))
        logging.info(f"After: {len(self.multiworld.itempool)}")

    def pre_fill(self) -> None:
        _ = [self.limited_state.collect(location.item, prevent_sweep=True) for location in self.get_locations() if
             location.item is not None and location.item.name not in stars and location.item.name != "Victory"]
        if not self.options.keysanity:
            keysanity_state = self.limited_state.copy()
            _ = [keysanity_state.collect(item, prevent_sweep=True) for items in self.limited_items for item in items]
            _ = [self.limited_state.collect(item, prevent_sweep=True) for items in self.keysanity_items for item in items]
            for i, locations in enumerate(self.keysanity_locations):
                fill_restrictive(self.multiworld, keysanity_state, locations, self.keysanity_items[i], single_player_placement=True, lock=True)
        for chapter in self.limited_chapters:
            fill_restrictive(self.multiworld, self.limited_state, list(self.limited_chapter_locations[chapter - 1]), self.limited_items[chapter - 1], single_player_placement=True, lock=True)
        fill_restrictive(self.multiworld, self.limited_state, list(self.limited_misc_locations), self.limited_misc_items, single_player_placement=True, lock=True)

    def set_rules(self) -> None:
        set_rules(self)
        set_tattle_rules(self)
        if self.options.goal == Goal.option_shadow_queen:
            self.multiworld.completion_condition[self.player] = lambda state: state.has("Victory", self.player)
        elif self.options.goal == Goal.option_crystal_stars:
            self.multiworld.completion_condition[self.player] = lambda state: state.has("stars", self.player, self.options.goal_stars.value)
        else:
            self.multiworld.completion_condition[self.player] = lambda state: state.can_reach("Pit of 100 Trials Floor 100: Return Postage", "Location", self.player)

    def fill_slot_data(self) -> Dict[str, Any]:
        return {
            "goal": self.options.goal.value,
            "goal_stars": self.options.goal_stars.value,
            "palace_stars": self.options.palace_stars.value,
            "pit_items": self.options.pit_items.value,
            "limit_chapter_logic": self.options.limit_chapter_logic.value,
            "limit_chapter_eight": self.options.limit_chapter_eight.value,
            "palace_skip": self.options.palace_skip.value,
            "yoshi_color": self.options.yoshi_color.value,
            "westside": self.options.open_westside.value,
            "tattlesanity": self.options.tattlesanity.value,
            "dazzle_rewards": self.options.dazzle_rewards.value,
            "star_shuffle": self.options.star_shuffle.value,
            "disable_intermissions": self.options.disable_intermissions.value,
            "cutscene_skip": self.options.cutscene_skip.value,
            "death_link": self.options.death_link.value,
            "piecesanity": self.options.piecesanity.value,
            "shinesanity": self.options.shinesanity.value
        }

    def create_item(self, name: str) -> TTYDItem:
        item = item_table.get(name, ItemData(None, name, "filler"))
        progression = (ItemClassification.useful if item.item_name == "Goombella" and not self.options.tattlesanity else item.progression)
        return TTYDItem(item.item_name, progression, item.id, self.player)

    def lock_vanilla_items_remove_from_pool(self, locations: LocationData | List[LocationData]) -> None:
        if isinstance(locations, LocationData):
            locations = [locations]
        for location in locations:
            if location.name not in self.disabled_locations:
                self.locked_item_frequencies[items_by_id[location.vanilla_item].item_name] = self.locked_item_frequencies.get(items_by_id[location.vanilla_item].item_name, 0) + 1
                item = self.create_item(items_by_id[location.vanilla_item].item_name)
                item.location = self.get_location(location.name)
                self.get_location(location.name).place_locked_item(item)

    def lock_filler_items_remove_from_pool(self, locations: LocationData | List[LocationData]) -> None:
        if isinstance(locations, LocationData):
            locations = [locations]
        for location in locations:
            if location.name not in self.disabled_locations:
                filler_item_name = self.get_filler_item_name()
                self.locked_item_frequencies[filler_item_name] = self.locked_item_frequencies.get(filler_item_name, 0) + 1
                item = self.create_item(filler_item_name)
                item.location = self.get_location(location.name)
                self.get_location(location.name).place_locked_item(item)

    def lock_item_remove_from_pool(self, location: str, item_name: str):
        if location not in self.disabled_locations:
            self.locked_item_frequencies[item_name] = self.locked_item_frequencies.get(item_name, 0) + 1
            item = self.create_item(item_name)
            item.location = self.get_location(location)
            self.get_location(location).place_locked_item(item)


    def get_filler_item_name(self) -> str:
        return self.random.choice(list(filter(lambda item: item.progression == ItemClassification.filler, itemList))).item_name

    def collect(self, state: "CollectionState", item: "Item") -> bool:
        change = super().collect(state, item)
        if change:
            if item.name in stars:
                state.prog_items[item.player]["stars"] += 1
            for star in self.required_chapters:
                if item.location is not None:
                    if item.name == stars[star - 1] and self.options.star_shuffle == StarShuffle.option_vanilla:
                        state.prog_items[item.player]["required_stars"] += 1
                        break
                    elif item.location.name == star_locations[star - 1] and self.options.star_shuffle == StarShuffle.option_stars_only:
                        state.prog_items[item.player]["required_stars"] += 1
                        break
        return change

    def remove(self, state: "CollectionState", item: "Item") -> bool:
        change = super().remove(state, item)
        if change:
            if item.name in stars:
                state.prog_items[item.player]["stars"] -= 1
            for star in self.required_chapters:
                if item.location is not None:
                    if item.name == stars[star - 1] and self.options.star_shuffle == StarShuffle.option_vanilla:
                        state.prog_items[item.player]["required_stars"] -= 1
                        break
                    elif item.location == star_locations[star - 1] and self.options.star_shuffle == StarShuffle.option_stars_only:
                        state.prog_items[item.player]["required_stars"] -= 1
                        break
        return change

    def generate_output(self, output_directory: str) -> None:
        patch = TTYDProcedurePatch(player=self.player, player_name=self.multiworld.player_name[self.player])
        write_files(self, patch)
        rom_path = os.path.join(
            output_directory, f"{self.multiworld.get_out_file_name_base(self.player)}" f"{patch.patch_file_ending}"
        )
        patch.write(rom_path)
