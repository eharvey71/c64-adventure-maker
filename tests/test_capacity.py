"""Tests for the text-runtime capacity counters.

The limits come from the DIM statements in legacy/advplay-c64-current.bas.
Overflow there is silent, so the editor's job is to say so while you are
authoring rather than after a build.
"""
import json
import re
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

import adventure_editor_v7 as ed  # noqa: E402


class TestLimitsMatchTheRuntime(unittest.TestCase):
    """Guard the numbers against drift from the BASIC source."""

    @classmethod
    def setUpClass(cls):
        cls.src = (REPO / "legacy" / "advplay-c64-current.bas").read_text()

    def dim_size(self, name):
        m = re.search(rf'dim {re.escape(name)}\((\d+)', self.src)
        self.assertIsNotNone(m, f"no DIM for {name}")
        return int(m.group(1))

    def test_rooms(self):
        self.assertEqual(ed.BASIC_LIMITS["rooms"], self.dim_size("r$"))

    def test_objects(self):
        self.assertEqual(ed.BASIC_LIMITS["objects"], self.dim_size("o$"))

    def test_vocabulary(self):
        self.assertEqual(ed.BASIC_LIMITS["vocabulary"], self.dim_size("v$"))

    def test_responses(self):
        self.assertEqual(ed.BASIC_LIMITS["responses"], self.dim_size("rs$"))

    def test_messages(self):
        self.assertEqual(ed.BASIC_LIMITS["messages"], self.dim_size("m$"))

    def test_flags(self):
        self.assertEqual(ed.BASIC_LIMITS["flags"], self.dim_size("f$"))

    def test_carried(self):
        self.assertEqual(ed.BASIC_LIMITS["carried"], self.dim_size("i$"))


class TestFlagCounting(unittest.TestCase):
    def flags(self, responses):
        return ed.basic_flag_names({"responses": responses})

    def test_counts_flags_that_are_set(self):
        self.assertEqual(
            self.flags([{"action": "SET FLAG.DEAD"}]), {"DEAD"})

    def test_counts_flags_that_are_only_tested(self):
        self.assertEqual(
            self.flags([{"condition": "FLAG.OPEN"}]), {"OPEN"})

    def test_sees_through_not(self):
        self.assertEqual(
            self.flags([{"condition": "NOT FLAG.DEAD"}]), {"DEAD"})

    def test_finds_flags_inside_comma_lists(self):
        self.assertEqual(
            self.flags([{"condition": "HAS KEY,NOT FLAG.DEAD,AT 7",
                         "action": "SET FLAG.WON,SCORE 10"}]),
            {"DEAD", "WON"})

    def test_the_same_flag_counts_once(self):
        self.assertEqual(
            self.flags([{"action": "SET FLAG.DEAD"},
                        {"condition": "FLAG.DEAD"}]), {"DEAD"})

    def test_no_flags_is_empty(self):
        self.assertEqual(self.flags([{"action": "SCORE 10"}]), set())


class TestCapacityAgainstTheSample(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(REPO / "example_castle.json") as f:
            cls.game = json.load(f)
        cls.caps = ed.basic_capacity(cls.game)

    def test_every_limit_is_reported(self):
        self.assertEqual(set(self.caps), set(ed.BASIC_LIMITS))

    def test_the_sample_fits_everywhere(self):
        for key, (count, limit) in self.caps.items():
            self.assertLessEqual(count, limit, key)

    def test_counts_match_the_file(self):
        self.assertEqual(self.caps["rooms"][0], len(self.game["rooms"]))
        self.assertEqual(self.caps["objects"][0], len(self.game["objects"]))
        self.assertEqual(self.caps["responses"][0], len(self.game["responses"]))

    def test_carried_counts_only_takeable_objects(self):
        takeable = [o for o in self.game["objects"].values()
                    if "TAKEABLE" in o.get("properties", "").upper()]
        self.assertEqual(self.caps["carried"][0], len(takeable))


class TestWording(unittest.TestCase):
    def test_under_the_limit_reads_as_usage(self):
        self.assertEqual(ed.capacity_text("rooms", 8, 20),
                         "8 of 20 rooms used in the text engine.")

    def test_over_the_limit_names_what_would_be_lost(self):
        text = ed.capacity_text("responses", 25, 20)
        self.assertIn("stops at 20", text)
        self.assertIn("last 5", text)

    def test_exactly_at_the_limit_is_not_an_overflow(self):
        self.assertNotIn("stops at", ed.capacity_text("rooms", 20, 20))

    def test_vocabulary_reads_naturally(self):
        self.assertIn("vocabulary entries", ed.capacity_text("vocabulary", 12, 20))

    def test_carried_is_phrased_as_advice_not_a_cap(self):
        under = ed.capacity_text("carried", 3, 10)
        self.assertIn("takeable objects", under)
        self.assertNotIn("stops at", under)

    def test_carried_over_the_limit_explains_the_consequence(self):
        self.assertIn("could not carry them all",
                      ed.capacity_text("carried", 14, 10))


if __name__ == "__main__":
    unittest.main()
