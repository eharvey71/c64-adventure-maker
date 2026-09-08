"""Tests for the move off the old system-message table.

WIN_GAME became a Game Settings field that both targets read. The other six
system messages were removed: the text engine printed its own built-in
strings and never consulted the table, and only two of the six ever reached
the graphical build.
"""
import json
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

import adventure_editor_v7 as ed  # noqa: E402


class TestWinTextReachesBothTargets(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(REPO / "example_castle.json") as f:
            cls.base = json.load(f)

    def game_with_win(self, text):
        g = json.loads(json.dumps(self.base))
        g["settings"]["winmessage"] = text
        return g

    def test_graphical_build_inlines_it(self):
        out = ed.Converter(self.game_with_win("THE CROWN IS YOURS!"),
                           crop_offset=0).emit()
        self.assertIn("THE CROWN IS YOURS!", out)

    def test_graphical_build_falls_back_when_unset(self):
        g = json.loads(json.dumps(self.base))
        g["settings"].pop("winmessage", None)
        out = ed.Converter(g, crop_offset=0).emit()
        self.assertIn("CONGRATULATIONS", out.upper())

    def test_player_uses_it_on_a_win(self):
        g = self.game_with_win("THE CROWN IS YOURS!")
        g["responses"] = [{"command": "USE LAMP", "condition": "",
                           "message": "", "action": "WINXXX"}]
        g["objects"]["LAMP"] = {"name": "LAMP", "description": "A LAMP.",
                                "start_room": 1, "properties": "TAKEABLE"}
        e = ed.GameEngine(g)
        msg, extras = e.execute_command("USE LAMP")
        self.assertTrue(any("CROWN" in x.upper() for x in extras + [msg]))

    def test_the_runtime_reads_it_from_settings(self):
        src = (REPO / "legacy" / "advplay-c64-current.bas").read_text()
        self.assertIn('k$="winmessage"', src)


class TestMigration(unittest.TestCase):
    """migrate_messages() runs on every load, so it must be safe to repeat."""

    class FakeApp:
        migrate_messages = ed.AdventureEditor.migrate_messages
        LEGACY_SYSTEM_MESSAGE_KEYS = ed.AdventureEditor.LEGACY_SYSTEM_MESSAGE_KEYS

        def __init__(self, game):
            self.game = game

    def migrate(self, game):
        app = self.FakeApp(game)
        return app.migrate_messages(), app.game

    def test_win_game_moves_into_settings(self):
        (moved, dropped), game = self.migrate(
            {"settings": {}, "messages": {"WIN_GAME": "YOU WIN!"}})
        self.assertEqual(moved, "YOU WIN!")
        self.assertEqual(game["settings"]["winmessage"], "YOU WIN!")
        self.assertNotIn("WIN_GAME", game["messages"])

    def test_the_other_six_are_dropped(self):
        msgs = {k: "x" for k in ed.AdventureEditor.LEGACY_SYSTEM_MESSAGE_KEYS}
        (_, dropped), game = self.migrate({"settings": {}, "messages": msgs})
        self.assertEqual(game["messages"], {})
        self.assertEqual(len(dropped), 7)

    def test_custom_messages_survive(self):
        (_, _), game = self.migrate({
            "settings": {},
            "messages": {"CANT_GO": "x", "WIZARD_GREETING": "HELLO."}})
        self.assertEqual(game["messages"], {"WIZARD_GREETING": "HELLO."})

    def test_an_existing_setting_is_not_overwritten(self):
        (moved, _), game = self.migrate({
            "settings": {"winmessage": "MINE"},
            "messages": {"WIN_GAME": "OLD"}})
        self.assertIsNone(moved)
        self.assertEqual(game["settings"]["winmessage"], "MINE")

    def test_running_twice_changes_nothing(self):
        game = {"settings": {}, "messages": {"WIN_GAME": "YOU WIN!",
                                             "GREETING": "HI."}}
        self.migrate(game)
        first = json.dumps(game, sort_keys=True)
        self.migrate(game)
        self.assertEqual(json.dumps(game, sort_keys=True), first)

    def test_a_game_with_no_messages_is_fine(self):
        (moved, dropped), game = self.migrate({"settings": {}})
        self.assertIsNone(moved)
        self.assertEqual(dropped, [])
        self.assertEqual(game["messages"], {})


class TestCustomMessagesStillWork(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(REPO / "example_castle.json") as f:
            cls.game = json.load(f)

    def test_the_sample_keeps_its_only_custom_message(self):
        self.assertIn("WIZARD_GREETING", self.game["messages"])

    def test_msg_action_inlines_into_the_graphical_build(self):
        out = ed.Converter(self.game, crop_offset=0).emit()
        self.assertIn("WIZARD LOOKS UP", out.upper())

    def test_msg_action_works_in_the_player(self):
        e = ed.GameEngine(self.game)
        e.current_room = 4
        _, extras = e.execute_command("TALK WIZARD")
        self.assertTrue(any("WIZARD LOOKS UP" in x.upper() for x in extras))

    def test_the_runtime_implements_the_msg_action(self):
        src = (REPO / "legacy" / "advplay-c64-current.bas").read_text()
        self.assertIn('="msg "', src)


if __name__ == "__main__":
    unittest.main()
