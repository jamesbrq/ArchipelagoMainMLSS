"""Loading-zone shuffle (generic ER) tests."""
from BaseClasses import EntranceType
from worlds.ttyd.Regions import (load_zones, get_shuffled_zone_names, build_warp_table,
                                 GROUP_DUNGEON_DOOR, GROUP_DUNGEON_OVERWORLD)
from . import TTYDTestBase


class ERBase(TTYDTestBase):
    options = {"loading_zone_shuffle": True}


class TestLoadingZoneShuffle(ERBase):
    def test_pairings_and_warp_table(self):
        world = self.world
        zones = load_zones()
        pairings = world.entrance_pairings
        self.assertTrue(pairings, "no entrance pairings recorded")

        pool = set(get_shuffled_zone_names(world))
        paired_exits = [exit_name for exit_name, _ in pairings]
        self.assertEqual(sorted(paired_exits), sorted(pool),
                         "every pooled zone must be placed exactly once")

        # Coupled symmetry: exit A -> target B implies exit B -> target A
        two_way = {(exit_name, target_name) for exit_name, target_name in pairings
                   if not target_name.endswith(" Landing")}
        for exit_name, target_name in two_way:
            self.assertIn((target_name, exit_name), two_way,
                          f"{exit_name} -> {target_name} has no reverse pairing")

        # One-way softlock constraint: no warp between (or within) trap rooms
        trap_rooms = {"steeple_boo_background", "glitzville_attic"}
        for exit_name, target_name in pairings:
            if target_name.endswith(" Landing"):
                source = zones[exit_name]
                destination = zones[target_name.removesuffix(" Landing")]
                self.assertFalse(source["src_region"] in trap_rooms
                                 and destination["region"] in trap_rooms,
                                 f"one-way {exit_name} -> {target_name} traps the player")

        # Warp table invariants
        table = world.warp_table
        valid_doors = {(zone["map"], zone["bero"]) for zone in zones.values()}
        for key, value in table.items():
            self.assertIn(key, valid_doors)
            self.assertIn(value, valid_doors)
        one_way_keys = {(zones[e]["map"], zones[e]["bero"]) for e, t in pairings
                        if t.endswith(" Landing")}
        two_way_keys = {(zones[zones[e]["target"]]["map"], zones[zones[e]["target"]]["bero"])
                        for e, t in pairings if not t.endswith(" Landing")}
        self.assertEqual(set(table), one_way_keys | two_way_keys)

    def test_all_entrances_connected(self):
        for region in self.multiworld.get_regions(self.player):
            for entrance in region.entrances:
                self.assertIsNotNone(entrance.parent_region, entrance.name)
            for exit_ in region.exits:
                self.assertIsNotNone(exit_.connected_region, exit_.name)

    def test_vanilla_zones_untouched(self):
        zones = load_zones()
        pool = set(get_shuffled_zone_names(self.world))
        tagged_vanilla = [zone["name"] for zone in zones.values() if "vanilla" in zone["tags"]]
        self.assertTrue(tagged_vanilla)
        for name in tagged_vanilla:
            self.assertNotIn(name, pool)


class TestUTReplay(ERBase):
    options = {"loading_zone_shuffle": True, "dungeon_shuffle": True}

    def test_replay_reproduces_layout(self):
        import json as json_module
        from test.general import setup_multiworld, gen_steps
        from worlds.AutoWorld import AutoWorldRegister, call_all

        world = self.multiworld.worlds[self.player]
        slot_data = world.fill_slot_data()
        # simulate the json round-trip Universal Tracker performs
        slot_data = json_module.loads(json_module.dumps(slot_data))

        world_type = AutoWorldRegister.world_types[self.game]
        # different seed on purpose: the replay path must not consume RNG
        second = setup_multiworld(world_type, steps=(), seed=(self.multiworld.seed or 0) + 1)
        second.re_gen_passthrough = {self.game: slot_data}
        for step in gen_steps:
            call_all(second, step)

        def layout(multiworld):
            return {exit_.name: exit_.connected_region.name
                    for region in multiworld.get_regions(1) for exit_ in region.exits}

        self.assertEqual(layout(self.multiworld), layout(second))
        self.assertEqual(world.warp_table, second.worlds[1].warp_table)


class TestDungeonShuffle(ERBase):
    options = {"loading_zone_shuffle": True, "dungeon_shuffle": True}

    def test_dungeon_groups_pair_across(self):
        world = self.world
        zones = load_zones()
        for exit_name, target_name in world.entrance_pairings:
            if target_name.endswith(" Landing"):
                continue
            source_tags = zones[exit_name]["tags"]
            target_tags = zones[target_name]["tags"]
            if "Dungeon Entrance" in source_tags:
                self.assertIn("Dungeon Exit", target_tags,
                              f"{exit_name} (dungeon door) paired with {target_name}")
            if "Dungeon Exit" in source_tags:
                self.assertIn("Dungeon Entrance", target_tags,
                              f"{exit_name} (overworld door) paired with {target_name}")


class TestWarpTxtSerialization(ERBase):
    options = {"loading_zone_shuffle": True}

    def test_round_trip(self):
        from Fill import distribute_items_restrictive
        from worlds.ttyd.Rom import TTYDProcedurePatch, write_files

        distribute_items_restrictive(self.multiworld)
        world = self.multiworld.worlds[self.player]
        patch = TTYDProcedurePatch(player=self.player,
                                   player_name=self.multiworld.player_name[self.player])
        write_files(world, patch)

        data = patch.get_file("warp.txt")
        parts = data.split(b"\x00")
        self.assertEqual(parts[-1], b"")
        self.assertEqual(parts[-2], b"")
        fields = [part.decode("utf-8") for part in parts[:-2]]
        self.assertEqual(len(fields) % 4, 0)
        parsed = {(fields[i], fields[i + 1]): (fields[i + 2], fields[i + 3])
                  for i in range(0, len(fields), 4)}
        self.assertEqual(parsed, world.warp_table)


class TestTRK3Tracker(ERBase):
    options = {"loading_zone_shuffle": True, "tattlesanity": True}

    def test_trk3_matches_entrance_graph(self):
        import struct
        import worlds.ttyd.Tracker as Tracker

        world = self.multiworld.worlds[self.player]
        original_format = Tracker.TRACKER_FORMAT
        Tracker.TRACKER_FORMAT = 3
        try:
            data = Tracker.build_tracker_bin(world)
        finally:
            Tracker.TRACKER_FORMAT = original_format

        (magic, region_count, display_count, location_count, connection_count, node_count,
         off_loc, off_conn, off_nodes, off_rules, off_strings, off_tattle) = \
            struct.unpack_from(">4sHHHHHIIIIII", data)
        self.assertEqual(magic, b"TRK3")

        regions = sorted(region.name for region in self.multiworld.get_regions(self.player))
        region_idx = {name: i for i, name in enumerate(regions)}
        self.assertEqual(region_count, len(regions))
        self.assertEqual(display_count, len(Tracker.REGIONS))
        self.assertEqual(node_count, len(Tracker.NODES))

        expected_edges = set()
        edge_counts = 0
        for region in self.multiworld.get_regions(self.player):
            for exit_ in region.exits:
                expected_edges.add((region_idx[region.name], region_idx[exit_.connected_region.name]))
                edge_counts += 1
        self.assertEqual(connection_count, edge_counts)

        parsed_edges = set()
        for i in range(connection_count):
            src, dst, rule_off = struct.unpack_from(">HHH", data, off_conn + 6 * i)
            self.assertLess(src, region_count)
            self.assertLess(dst, region_count)
            self.assertTrue(rule_off == 0xFFFF or rule_off < off_strings - off_rules)
            parsed_edges.add((src, dst))
        self.assertEqual(parsed_edges, expected_edges)

        for i in range(location_count):
            (name_off, rule_off, region, gsw_type, gsw_id, gsw_value, flags,
             disp_group) = struct.unpack_from(">HHHBHBBB", data, off_loc + 14 * i)
            self.assertLess(region, region_count)
            self.assertLess(disp_group, display_count)


class TestERWithLimitedChapters(ERBase):
    options = {"loading_zone_shuffle": True, "limit_chapter_logic": True,
               "limit_chapter_eight": True}


class TestERWithPalaceSkip(ERBase):
    options = {"loading_zone_shuffle": True, "palace_skip": True}


class TestERNoBluePipes(ERBase):
    options = {"loading_zone_shuffle": True, "blue_pipe_toggle": False}


class TestERKitchenSink(ERBase):
    options = {"loading_zone_shuffle": True, "dungeon_shuffle": True,
               "tattlesanity": True, "troublesanity": True, "cooksanity": True,
               "open_westside": True, "limit_chapter_logic": True}
