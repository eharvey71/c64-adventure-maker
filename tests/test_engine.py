"""Behaviour tests for the in-editor GameEngine (the Player tab).

These pin the parser and world-model rules the engine mirrors from the
original BASIC runtime, so playtesting stays consistent with what the
built C64 disk actually does.
"""
import json
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

import adventure_editor_v7 as ed  # noqa: E402


def sample_engine():
    with open(REPO / "example_castle.json") as f:
        return ed.GameEngine(json.load(f))


class TestEngineBasics(unittest.TestCase):
    def setUp(self):
        self.e = sample_engine()

    def test_starts_in_configured_room(self):
        self.assertEqual(self.e.current_room, 1)

    def test_engine_does_not_mutate_the_source_game(self):
        with open(REPO / "example_castle.json") as f:
            data = json.load(f)
        before = json.dumps(data, sort_keys=True)
        e = ed.GameEngine(data)
        e.execute_command("TAKE SWORD")
        e.execute_command("LOOK")
        self.assertEqual(json.dumps(data, sort_keys=True), before)

    def test_look_reports_current_room(self):
        msg, _ = self.e.execute_command("LOOK")
        self.assertIn("FOREST PATH", msg)

    def test_empty_input_is_handled(self):
        msg, _ = self.e.execute_command("   ")
        self.assertTrue(msg)
        self.assertFalse(self.e.game_over)

    def test_unknown_command_does_not_crash_or_end_game(self):
        msg, _ = self.e.execute_command("XYZZY PLUGH")
        self.assertIn("UNDERSTAND", msg.upper())
        self.assertFalse(self.e.game_over)

    def test_quit_sets_game_over(self):
        self.e.execute_command("QUIT")
        self.assertTrue(self.e.game_over)

    def test_score_reports_out_of_maxscore(self):
        msg, _ = self.e.execute_command("SCORE")
        self.assertIn(str(self.e.max_score), msg)

    def test_commands_are_case_insensitive(self):
        a, _ = sample_engine().execute_command("look")
        b, _ = sample_engine().execute_command("LOOK")
        self.assertEqual(a, b)


class TestInventory(unittest.TestCase):
    def setUp(self):
        self.e = sample_engine()

    def test_inventory_starts_empty(self):
        msg, _ = self.e.execute_command("I")
        self.assertIn("CARRYING", msg.upper())
        self.assertEqual(self.e.inventory_objects(), [])

    def test_take_then_carry(self):
        self.e.execute_command("TAKE SWORD")
        carried = [oid for oid, _ in self.e.inventory_objects()]
        self.assertIn("SWORD", carried)

    def test_drop_returns_object_to_current_room(self):
        self.e.execute_command("TAKE SWORD")
        self.e.execute_command("DROP SWORD")
        self.assertEqual(self.e.inventory_objects(), [])
        here = [oid for oid, _ in self.e.room_objects()]
        self.assertIn("SWORD", here)

    def test_taking_absent_object_is_refused(self):
        e = sample_engine()
        msg, _ = e.execute_command("TAKE CHALICE")
        self.assertEqual(e.inventory_objects(), [])
        self.assertTrue(msg)

    def test_carried_object_moves_between_rooms(self):
        self.e.execute_command("TAKE SWORD")
        start = self.e.current_room
        for direction in ("N", "S", "E", "W"):
            self.e.execute_command(direction)
            if self.e.current_room != start:
                break
        else:
            self.skipTest("start room has no usable exit")
        carried = [oid for oid, _ in self.e.inventory_objects()]
        self.assertIn("SWORD", carried)


class TestMovement(unittest.TestCase):
    def test_blocked_exit_reports_and_does_not_move(self):
        e = sample_engine()
        before = e.current_room
        msg, _ = e.execute_command("N")
        if e.current_room == before:
            self.assertIn("CAN'T GO", msg.upper())

    def test_long_and_short_direction_words_agree(self):
        a, b = sample_engine(), sample_engine()
        a.execute_command("E")
        b.execute_command("EAST")
        self.assertEqual(a.current_room, b.current_room)

    def test_every_exit_leads_to_a_declared_room(self):
        e = sample_engine()
        for rid, room in e.game["rooms"].items():
            for dest in room.get("exits", []):
                if dest in (0, "0", "", None):
                    continue
                self.assertIn(str(dest), e.game["rooms"],
                              f"room {rid} exits to undeclared room {dest}")


class TestDebugAndState(unittest.TestCase):
    def test_debug_log_is_bounded(self):
        e = sample_engine()
        for _ in range(400):
            e.execute_command("LOOK")
        self.assertLessEqual(len(e.debug_log), 200)

    def test_flags_start_empty(self):
        self.assertEqual(sample_engine().flags, [])

    def test_missing_message_falls_back_to_system_default(self):
        e = sample_engine()
        e.game["messages"] = {}
        self.assertEqual(e.get_msg("CANT_GO"),
                         ed.GameEngine.SYSTEM_DEFAULTS["CANT_GO"])


class TestMinimalGame(unittest.TestCase):
    """A hand-built two-room game, so behaviour is not tied to the sample."""

    GAME = {
        "settings": {"startroom": 1, "maxscore": 10, "title": "T"},
        "rooms": {
            "1": {"name": "HALL", "description": "A HALL.",
                  "exits": [2, 0, 0, 0]},
            "2": {"name": "CAVE", "description": "A CAVE.",
                  "exits": [0, 1, 0, 0]},
        },
        "objects": {
            "LAMP": {"name": "LAMP", "description": "A LAMP.",
                     "start_room": 1, "properties": "TAKEABLE"},
            "STATUE": {"name": "STONE STATUE", "description": "A STATUE.",
                       "start_room": 1, "properties": "FIXED"},
        },
        "vocabulary": {}, "messages": {}, "responses": [],
    }

    def test_walk_north_and_back(self):
        e = ed.GameEngine(self.GAME)
        e.execute_command("N")
        self.assertEqual(e.current_room, 2)
        e.execute_command("S")
        self.assertEqual(e.current_room, 1)

    def test_object_visible_only_in_its_room(self):
        e = ed.GameEngine(self.GAME)
        self.assertIn("LAMP", [o for o, _ in e.room_objects()])
        e.execute_command("N")
        self.assertNotIn("LAMP", [o for o, _ in e.room_objects()])

    def test_take_and_carry_across_rooms(self):
        e = ed.GameEngine(self.GAME)
        e.execute_command("TAKE LAMP")
        e.execute_command("N")
        self.assertIn("LAMP", [o for o, _ in e.inventory_objects()])
        # a carried object is not also lying in the room
        self.assertNotIn("LAMP", [o for o, _ in e.room_objects()])

    def test_fixed_object_cannot_be_taken(self):
        e = ed.GameEngine(self.GAME)
        e.execute_command("TAKE STATUE")
        self.assertNotIn("STATUE", [o for o, _ in e.inventory_objects()])


class TestParityWithTheTextRuntime(unittest.TestCase):
    """The Player must show what a .adv build will actually do.

    Each of these mirrors a rule in legacy/advplay-c64-current.bas that was
    confirmed in VICE, so the two cannot drift apart unnoticed.
    """

    def setUp(self):
        self.e = sample_engine()

    # -- NOT on conditions (runtime line 14410) --------------------------
    def test_not_inverts_a_flag_condition(self):
        self.e.current_room = 7
        self.assertTrue(self.e.check_condition("NOT FLAG.BEAST_DEAD"))
        self.e.flags.append("BEAST_DEAD")
        self.assertFalse(self.e.check_condition("NOT FLAG.BEAST_DEAD"))

    def test_not_combines_with_other_terms(self):
        self.e.current_room = 7
        self.assertTrue(self.e.check_condition("NOT FLAG.BEAST_DEAD,AT 7"))
        self.assertFalse(self.e.check_condition("NOT FLAG.BEAST_DEAD,AT 4"))

    def test_not_on_a_has_condition(self):
        self.assertTrue(self.e.check_condition("NOT HAS SWORD"))
        self.e.game["objects"]["SWORD"]["start_room"] = -1
        self.assertFalse(self.e.check_condition("NOT HAS SWORD"))

    # -- any verb reaches the response table (runtime line 5396) ---------
    def test_hit_reaches_the_response_table(self):
        e = sample_engine(); e.current_room = 7
        e.game["objects"]["SWORD"]["start_room"] = -1
        msg, _ = e.execute_command("HIT BEAST")
        self.assertIn("SLASH", msg.upper())

    def test_hit_still_respects_its_condition(self):
        e = sample_engine(); e.current_room = 7      # no sword carried
        msg, _ = e.execute_command("HIT BEAST")
        self.assertNotIn("SLASH", msg.upper())

    def test_talk_reaches_the_response_table(self):
        e = sample_engine(); e.current_room = 4
        msg, extras = e.execute_command("TALK WIZARD")
        self.assertTrue(any("WIZARD LOOKS UP" in x.upper() for x in extras))

    def test_an_invented_verb_reaches_the_response_table(self):
        e = sample_engine()
        e.game["responses"].append(
            {"command": "RUB LAMP", "condition": "", "message": "IT GLOWS.",
             "action": ""})
        msg, _ = e.execute_command("RUB LAMP")
        self.assertEqual(msg, "IT GLOWS.")

    def test_a_genuinely_unknown_command_is_still_refused(self):
        msg, _ = self.e.execute_command("XYZZY PLUGH")
        self.assertIn("UNDERSTAND", msg.upper())

    # -- filler words (runtime routine at 7200) --------------------------
    def test_filler_words_are_dropped(self):
        for phrasing in ("GIVE CHALICE WIZARD",
                         "GIVE CHALICE TO WIZARD",
                         "GIVE THE CHALICE TO THE WIZARD"):
            e = sample_engine(); e.current_room = 4
            e.game["objects"]["TREASURE"]["start_room"] = -1
            msg, _ = e.execute_command(phrasing)
            self.assertIn("PRESENT", msg.upper(), phrasing)

    def test_the_verb_itself_is_never_treated_as_filler(self):
        # "AT" is a filler word, but a command starting with it keeps it.
        self.assertEqual(self.e.expand_input("AT LAMP").split()[0], "AT")

    def test_filler_stripping_survives_synonym_expansion(self):
        e = sample_engine()
        self.assertEqual(e.expand_input("X AT THE SWORD"), "EXAMINE SWORD")


if __name__ == "__main__":
    unittest.main()
