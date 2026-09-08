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
    def test_any_verb_now_reaches_the_response_table(self):
        for verb in ("EXAMINE", "TALK", "HIT", "GIVE", "USE", "RUB", "XYZZY"):
            self.assertEqual(
                ed.basic_incompatibilities(resp(command=f"{verb} THING")), [],
                f"{verb} should reach the response table")

    def test_empty_command_is_flagged(self):
        self.assertTrue(ed.basic_incompatibilities(resp(command="   ")))


class TestConditionRules(unittest.TestCase):
    def test_comma_lists_are_accepted(self):
        self.assertEqual(
            ed.basic_incompatibilities(resp(condition="HAS SWORD,AT 7")), [])

    def test_at_and_not_are_accepted(self):
        for cond in ("AT 4", "NOT FLAG.DEAD", "NOT FLAG.DEAD,AT 7",
                     "HAS KEY,NOT FLAG.OPEN,AT 2"):
            self.assertEqual(ed.basic_incompatibilities(resp(condition=cond)),
                             [], cond)

    def test_a_genuinely_unknown_condition_is_still_flagged(self):
        problems = ed.basic_incompatibilities(resp(condition="WEATHER SUNNY"))
        self.assertTrue(any("does not understand" in p for p in problems))

    def test_each_bad_term_reports_once(self):
        problems = ed.basic_incompatibilities(
            resp(condition="HAS KEY,WEATHER SUNNY,MOOD GLAD"))
        self.assertEqual(len(problems), 2)

    def test_empty_condition_is_fine(self):
        self.assertEqual(ed.basic_incompatibilities(resp(condition="")), [])


class TestActionRules(unittest.TestCase):
    def test_comma_lists_run_in_full(self):
        self.assertEqual(ed.basic_incompatibilities(
            resp(action="SET FLAG.DEAD,REMOVE BEAST,UNLOCK SOUTH 7 TO 8,SCORE 50")),
            [])

    def test_remove_and_msg_are_implemented(self):
        for action in ("REMOVE BEAST", "MSG GREETING"):
            self.assertEqual(ed.basic_incompatibilities(resp(action=action)),
                             [], action)

    def test_a_genuinely_unknown_action_is_still_flagged(self):
        problems = ed.basic_incompatibilities(resp(action="TELEPORT 4"))
        self.assertTrue(any("has no" in p for p in problems))

    def test_empty_action_is_fine(self):
        self.assertEqual(ed.basic_incompatibilities(resp(action="")), [])


class TestAgainstTheShippedSample(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(REPO / "example_castle.json") as f:
            cls.responses = json.load(f)["responses"]

    def test_every_response_now_runs_in_both_targets(self):
        bad = {r["command"]: ed.basic_incompatibilities(r)
               for r in self.responses if ed.basic_incompatibilities(r)}
        self.assertEqual(bad, {})

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

    def test_condition_prefixes(self):
        self.assertEqual(set(ed.BASIC_CONDITION_PREFIXES),
                         {"HAS ", "FLAG.", "AT ", "NOT "})

    def test_action_prefixes_cover_every_implemented_action(self):
        self.assertEqual(set(ed.BASIC_ACTION_PREFIXES),
                         {"UNLOCK ", "MOVE TO ", "SET FLAG.", "SCORE ",
                          "WIN", "REMOVE ", "MSG "})

    def test_the_runtime_still_dispatches_exactly_these_actions(self):
        src = (REPO / "legacy" / "advplay-c64-current.bas").read_text()
        for token in ("unlock ", "move to ", "set flag.", "win", "score ",
                      "remove ", "msg "):
            self.assertIn(f'="{token}"', src,
                          f"runtime no longer dispatches {token!r}")

    def test_the_runtime_evaluates_condition_terms(self):
        src = (REPO / "legacy" / "advplay-c64-current.bas").read_text()
        for token in ("has ", "flag.", "at ", "not "):
            self.assertIn(f'="{token}"', src,
                          f"runtime no longer evaluates {token!r}")


if __name__ == "__main__":
    unittest.main()


class TestUndefinedNouns(unittest.TestCase):
    """A noun with no object behind it still works, but the author can do
    better by declaring it, and the editor should say so."""

    GAME = {"objects": {
        "SWORD": {"name": "RUSTY SWORD", "properties": "TAKEABLE"},
        "GATE":  {"name": "IRON GATE",   "properties": "FIXED"},
    }}

    def test_a_declared_object_is_not_flagged(self):
        self.assertEqual(
            ed.undefined_nouns({"command": "USE SWORD"}, self.GAME), [])

    def test_matching_on_the_display_name_counts_as_declared(self):
        self.assertEqual(
            ed.undefined_nouns({"command": "USE GATE"}, self.GAME), [])

    def test_a_word_from_the_display_name_counts_as_declared(self):
        self.assertEqual(
            ed.undefined_nouns({"command": "USE RUSTY"}, self.GAME), [])

    def test_an_unknown_noun_is_flagged(self):
        self.assertEqual(
            ed.undefined_nouns({"command": "TALK WIZARD"}, self.GAME), ["WIZARD"])

    def test_filler_words_are_not_mistaken_for_nouns(self):
        self.assertEqual(
            ed.undefined_nouns({"command": "GIVE SWORD TO GATE"}, self.GAME), [])

    def test_the_verb_is_never_flagged(self):
        self.assertNotIn("TALK",
                         ed.undefined_nouns({"command": "TALK SWORD"}, self.GAME))

    def test_the_note_names_the_room_from_an_at_condition(self):
        note = ed.undefined_noun_note(
            "WIZARD", {"command": "TALK WIZARD", "condition": "AT 4"})
        self.assertIn("room 4", note)
        self.assertIn("FIXED", note)

    def test_the_note_warns_when_there_is_no_at_condition(self):
        note = ed.undefined_noun_note(
            "WIZARD", {"command": "TALK WIZARD", "condition": ""})
        self.assertIn("left out entirely", note)

    def test_declaring_the_object_removes_the_note(self):
        game = dict(self.GAME)
        game = {"objects": dict(self.GAME["objects"])}
        self.assertTrue(ed.undefined_nouns({"command": "TALK WIZARD"}, game))
        game["objects"]["WIZARD"] = {"name": "WIZARD", "properties": "FIXED"}
        self.assertEqual(ed.undefined_nouns({"command": "TALK WIZARD"}, game), [])

    def test_the_sample_flags_only_the_wizard(self):
        with open(REPO / "example_castle.json") as f:
            game = json.load(f)
        found = {w for r in game["responses"] for w in ed.undefined_nouns(r, game)}
        self.assertEqual(found, {"WIZARD"})


class TestHiddenObjects(unittest.TestCase):
    """A HIDDEN object is present and interactable but never listed, so an
    undeclared noun can become a real object without spoiling a secret."""

    def game(self, props):
        return {"settings": {"startroom": 1}, "vocabulary": {}, "messages": {},
                "responses": [],
                "rooms": {"1": {"name": "R", "description": "D",
                                "exits": [0, 0, 0, 0]}},
                "objects": {"THING": {"name": "THING", "start_room": 1,
                                      "description": "A THING.",
                                      "properties": props}}}

    def emitted_class(self, props):
        out = ed.Converter(self.game(props), crop_offset=0).emit()
        for line in out.splitlines():
            if line.endswith(":thing"):
                return line.split(":")[0]
        return None

    def test_hidden_uses_the_unlisted_class(self):
        self.assertEqual(self.emitted_class("HIDDEN"), "scenery")

    def test_fixed_stays_listed(self):
        self.assertEqual(self.emitted_class("FIXED"), "sceneryobj")

    def test_takeable_stays_takeable(self):
        self.assertEqual(self.emitted_class("TAKEABLE"), "normalobj")

    def test_a_synthesized_stand_in_is_also_unlisted(self):
        with open(REPO / "example_castle.json") as f:
            g = json.load(f)
        out = ed.Converter(g, crop_offset=0).emit()
        self.assertIn("scenery:wizard", out)
        self.assertNotIn("sceneryobj:wizard", out)

    def test_the_text_runtime_skips_hidden_in_the_room_listing(self):
        src = (REPO / "legacy" / "advplay-c64-current.bas").read_text()
        line = [l for l in src.splitlines() if l.startswith("6060 ")][0]
        self.assertIn('<>"hidden"', line)

    def test_hidden_is_not_takeable_in_the_text_runtime(self):
        # the take check accepts only "takeable", so HIDDEN cannot be picked up
        src = (REPO / "legacy" / "advplay-c64-current.bas").read_text()
        self.assertIn('if o$(i,3)<>"takeable"', src)

    def test_the_player_does_not_list_a_hidden_object(self):
        g = self.game("HIDDEN")
        e = ed.GameEngine(g)
        self.assertNotIn("THING", e.room_description().upper().split("YOU SEE")[-1]
                         if "YOU SEE" in e.room_description().upper() else "")

    def test_the_player_can_still_examine_a_hidden_object(self):
        e = ed.GameEngine(self.game("HIDDEN"))
        msg, _ = e.execute_command("EXAMINE THING")
        self.assertIn("A THING.", msg.upper())


class TestAdoption(unittest.TestCase):
    adopt = staticmethod(ed.AdventureEditor.adopt_undefined_nouns)

    class FakeApp:
        adopt_undefined_nouns = ed.AdventureEditor.adopt_undefined_nouns
        def __init__(self, game): self.game = game

    def run_adopt(self, game):
        app = self.FakeApp(game)
        return app.adopt_undefined_nouns(), app.game

    def test_an_undeclared_noun_becomes_a_hidden_object(self):
        added, game = self.run_adopt({
            "objects": {},
            "responses": [{"command": "TALK WIZARD", "condition": "AT 4"}]})
        self.assertEqual(added, ["WIZARD"])
        self.assertEqual(game["objects"]["WIZARD"]["properties"], "HIDDEN")
        self.assertEqual(game["objects"]["WIZARD"]["start_room"], 4)

    def test_it_needs_an_at_condition_to_know_the_room(self):
        added, game = self.run_adopt({
            "objects": {},
            "responses": [{"command": "TALK WIZARD", "condition": ""}]})
        self.assertEqual(added, [])
        self.assertEqual(game["objects"], {})

    def test_a_declared_object_is_left_alone(self):
        added, game = self.run_adopt({
            "objects": {"WIZARD": {"name": "W", "properties": "FIXED"}},
            "responses": [{"command": "TALK WIZARD", "condition": "AT 4"}]})
        self.assertEqual(added, [])
        self.assertEqual(game["objects"]["WIZARD"]["properties"], "FIXED")

    def test_running_twice_adds_nothing_further(self):
        game = {"objects": {},
                "responses": [{"command": "TALK WIZARD", "condition": "AT 4"}]}
        self.run_adopt(game)
        added, _ = self.run_adopt(game)
        self.assertEqual(added, [])

    def test_an_authored_description_is_not_overwritten(self):
        game = {"objects": {},
                "responses": [{"command": "TALK WIZARD", "condition": "AT 4"}]}
        self.run_adopt(game)
        game["objects"]["WIZARD"]["description"] = "A STOOPED FIGURE."
        self.run_adopt(game)
        self.assertEqual(game["objects"]["WIZARD"]["description"],
                         "A STOOPED FIGURE.")
