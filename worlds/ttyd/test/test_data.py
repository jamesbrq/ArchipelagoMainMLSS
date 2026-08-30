"""Integrity checks for the region/zone/location data files."""
import json
import pkgutil
import unittest

import worlds.ttyd.Regions as Regions
from worlds.ttyd.Items import item_table
from worlds.ttyd.Locations import all_locations, shadow_queen


class TestRegionData(unittest.TestCase):
    def setUp(self):
        self.regions = Regions.load_regions()
        self.zones = Regions.load_zones()
        self.region_tags = {region["tag"] for region in self.regions}
        self.region_names = {region["name"] for region in self.regions}

    def test_region_tags_and_names_unique(self):
        self.assertEqual(len(self.region_tags), len(self.regions))
        self.assertEqual(len(self.region_names), len(self.regions))

    def test_every_location_has_exactly_one_region_tag(self):
        synthetic = {location.name for location in shadow_queen}
        for location in all_locations:
            if location.name in synthetic:
                continue  # attached to the Shadow Queen region directly
            tags = [tag for tag in location.tags if tag in self.region_tags]
            self.assertEqual(len(tags), 1, f"{location.name}: region tags {tags}")

    def test_zone_regions_resolve(self):
        for zone in self.zones.values():
            self.assertIn(zone["region"], self.region_tags, zone["name"])
            if zone["target"] == "One Way":
                self.assertIn(zone["src_region"], self.region_tags, zone["name"])

    def test_two_way_zones_symmetric(self):
        for zone in self.zones.values():
            if zone["target"] == "One Way":
                continue
            partner = self.zones.get(zone["target"])
            self.assertIsNotNone(partner, f"{zone['name']}: target {zone['target']} missing")
            self.assertEqual(partner["target"], zone["name"],
                             f"{zone['name']} <-> {partner['name']} asymmetric")

    def test_zone_names_unique_and_maps_present(self):
        for zone in self.zones.values():
            self.assertTrue(zone["map"], zone["name"])
            self.assertTrue(zone["bero"], zone["name"])

    def test_rule_items_and_regions_valid(self):
        valid_functions = {"PalaceAccess", "PalaceAccessGoal", "key_any", "key_both",
                           "riddle_tower", "super_boots", "super_hammer", "tube_curse",
                           "ultra_boots", "ultra_hammer", "pit", "chapter_completions"}
        location_names = {location.name for location in all_locations}

        def check(rule, context):
            if rule is None or rule is False or rule is True:
                return
            self.assertIsInstance(rule, dict, context)
            for key, value in rule.items():
                if key in ("and", "or"):
                    for sub in value:
                        check(sub, context)
                elif key == "has":
                    item = value if isinstance(value, str) else value["item"]
                    self.assertIn(item, item_table, f"{context}: unknown item {item}")
                elif key == "function":
                    name = value if isinstance(value, str) else value["name"]
                    self.assertIn(name, valid_functions, f"{context}: unknown function {name}")
                elif key == "can_reach_region":
                    self.assertIn(value, self.region_names, f"{context}: unknown region {value}")
                elif key == "can_reach":
                    self.assertIn(value, location_names, f"{context}: unknown location {value}")
                elif key == "count":
                    pass
                else:
                    self.fail(f"{context}: unknown rule key {key}")

        for zone in self.zones.values():
            check(zone["rules"], f"zone {zone['name']}")
