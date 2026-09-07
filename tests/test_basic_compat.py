"""Tests for the text-engine compatibility check shown in the Responses tab.

Every rule asserted here was established by reading
legacy/advplay-c64-current.bas and confirming the behaviour in VICE, so these
tests are the record of what that runtime actually does.
"""
import json
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

import adventure_editor_v7 as ed  # noqa: E402


def resp(command="USE LAMP", condition="", message="M", action=""):
    return {"command": command, "condition": condition,
            "message": message, "action": action}


class TestCompatibleResponses(unittest.TestCase):
    def test_bare_use(self):
        self.assertEqual(ed.basic_incompatibilities(resp()), [])

    def test_use_with_has_condition(self):
        self.assertEqual(ed.basic_incompatibilities(resp(condition="HAS KEY")), [])

    def test_use_with_flag_condition(self):
        self.assertEqual(ed.basic_incompatibilities(resp(condition="FLAG.LIT")), [])

    def test_every_action_the_runtime_implements(self):
        for action in ("UNLOCK WEST 2 TO 6", "MOVE TO 4", "SET FLAG.X",
                       "SCORE 50", "WIN"):
            self.assertEqual(ed.basic_incompatibilities(resp(action=action)), [],
                             f"{action} should work in the text engine")

    def test_case_and_padding_are_ignored(self):
        self.assertEqual(
            ed.basic_incompatibilities(
                resp(command="  use lamp ", condition=" has key ",
                     action=" score 10 ")), [])


class TestVerbRules(unittest.TestCase):
    def test_non_use_verbs_are_flagged(self):
        for verb in ("EXAMINE", "TALK", "HIT", "GIVE", "TAKE", "DROP"):
            problems = ed.basic_incompatibilities(resp(command=f"{verb} THING"))
            self.assertTrue(any("only consults responses for USE" in p
                                for p in problems), f"{verb} not flagged")

    def test_article_agrees_with_the_verb(self):
        self.assertIn("an EXAMINE response",
                      ed.basic_incompatibilities(resp(command="EXAMINE X"))[0])
        self.assertIn("a TALK response",
                      ed.basic_incompatibilities(resp(command="TALK X"))[0])

    def test_empty_command_is_flagged(self):
        self.assertTrue(ed.basic_incompatibilities(resp(command="   ")))


class TestConditionRules(unittest.TestCase):
    def test_comma_list_is_flagged(self):
        problems = ed.basic_incompatibilities(resp(condition="HAS SWORD,AT 7"))
        self.assertTrue(any("one condition only" in p for p in problems))

    def test_unknown_condition_is_flagged_as_silently_true(self):
        problems = ed.basic_incompatibilities(resp(condition="AT 4"))
        self.assertTrue(any("treated as true" in p for p in problems))

    def test_empty_condition_is_fine(self):
        self.assertEqual(ed.basic_incompatibilities(resp(condition="")), [])

    def test_a_comma_list_reports_once_not_twice(self):
        # It is one defect, not "comma" plus "unknown prefix".
        problems = ed.basic_incompatibilities(resp(condition="HAS SWORD,AT 7"))
        self.assertEqual(len(problems), 1)


class TestActionRules(unittest.TestCase):
    def test_comma_list_names_the_survivor(self):
        problems = ed.basic_incompatibilities(
            resp(action="SET FLAG.DEAD,REMOVE BEAST,SCORE 50"))
        self.assertEqual(len(problems), 1)
        self.assertIn("SET FLAG.DEAD", problems[0])

    def test_unimplemented_actions_are_flagged(self):
        for action in ("REMOVE BEAST", "MSG GREETING"):
            problems = ed.basic_incompatibilities(resp(action=action))
            self.assertTrue(any("has no" in p for p in problems), action)

    def test_empty_action_is_fine(self):
        self.assertEqual(ed.basic_incompatibilities(resp(action="")), [])


class TestAgainstTheShippedSample(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(REPO / "example_castle.json") as f:
            cls.responses = json.load(f)["responses"]

    def test_only_the_one_use_response_survives(self):
        ok = [r for r in self.responses if not ed.basic_incompatibilities(r)]
        self.assertEqual([r["command"] for r in ok], ["USE KEY GATE"])

    def test_every_response_is_classified_without_error(self):
        for r in self.responses:
            self.assertIsInstance(ed.basic_incompatibilities(r), list)

    def test_reasons_are_whole_sentences(self):
        for r in self.responses:
            for p in ed.basic_incompatibilities(r):
                self.assertTrue(p[0].isupper(), f"not a sentence: {p}")
                self.assertTrue(p.endswith("."), f"not a sentence: {p}")


class TestRuleTablesMatchTheRuntime(unittest.TestCase):
    """Guard the constants against drift from the BASIC source."""

    def test_only_use_reaches_the_response_table(self):
        self.assertEqual(ed.BASIC_RESPONSE_VERBS, {"USE"})

    def test_condition_prefixes(self):
        self.assertEqual(set(ed.BASIC_CONDITION_PREFIXES), {"HAS ", "FLAG."})

    def test_action_prefixes_cover_the_five_implemented_actions(self):
        self.assertEqual(set(ed.BASIC_ACTION_PREFIXES),
                         {"UNLOCK ", "MOVE TO ", "SET FLAG.", "SCORE ", "WIN"})

    def test_the_runtime_still_dispatches_exactly_these_actions(self):
        src = (REPO / "legacy" / "advplay-c64-current.bas").read_text()
        for token in ("unlock ", "move to ", "set flag.", "win", "score "):
            self.assertIn(f'="{token}"', src,
                          f"runtime no longer dispatches {token!r}")


if __name__ == "__main__":
    unittest.main()
