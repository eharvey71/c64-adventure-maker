"""
Two things the BASIC runtime does that the graphical target used to skip:
show the room's exits, and honour the author's vocabulary synonyms.
"""
import json
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

import adventure_editor_v7 as ed  # noqa: E402


def game(**over):
    g = {
        "settings": {"title": "T", "author": "A", "version": "1", "startroom": 1},
        "rooms": {
            "1": {"name": "ONE", "description": "D1", "exits": [0, 2, 0, 0]},
            "2": {"name": "TWO", "description": "D2", "exits": [1, 0, 0, 0]},
            "3": {"name": "THREE", "description": "D3", "exits": [0, 0, 0, 0]},
        },
        "objects": {"KEY": {"name": "BRASS KEY", "start_room": 1,
                            "description": "K", "properties": "TAKEABLE"}},
        "vocabulary": {},
        "messages": {},
        "responses": [],
        "scenes": {},
    }
    g.update(over)
    return g


def emit(g):
    return ed.Converter(g).emit()


def room_block(script, name):
    """The lines belonging to one room:... block."""
    out, keep = [], False
    for line in script.splitlines():
        if line.startswith("room:") or line.startswith(("verb:", "scenery:",
                                                        "normalobj:",
                                                        "sceneryobj:")):
            keep = line == f"room:{name}"
            if keep:
                continue
        if keep:
            out.append(line)
    return out


class TestExitsAreShown(unittest.TestCase):
    """stdlib's own onenter prints the description and the objects but never
    the exits, so a room had to spell the directions out in its prose."""

    def test_a_room_lists_its_open_directions(self):
        b = room_block(emit(game()), "room1")
        self.assertIn("\t\tmsg:EXITS: SOUTH", b)

    def test_a_dead_end_says_none(self):
        b = room_block(emit(game()), "room3")
        self.assertIn("\t\tmsg:EXITS: NONE", b)

    def test_directions_read_in_the_same_order_as_the_basic_runtime(self):
        g = game()
        g["rooms"]["1"]["exits"] = [2, 2, 2, 2]
        b = room_block(emit(g), "room1")
        self.assertIn("\t\tmsg:EXITS: NORTH, SOUTH, EAST, WEST", b)

    def test_both_onfirst_and_onenter_are_emitted(self):
        # they are separate handlers - 'onfirst+onenter' is only valid at
        # the top level, and a room with only onenter shows no exits on the
        # first visit
        b = room_block(emit(game()), "room1")
        self.assertIn("\tonfirst", b)
        self.assertIn("\tonenter", b)

    def test_the_stdlib_body_is_repeated_not_replaced(self):
        # a room-scoped handler wins over stdlib's $everywhere one, so it
        # has to print the description and list the objects itself
        b = room_block(emit(game()), "room1")
        self.assertIn("\t\tmsg:$roomdesc", b)
        self.assertIn("\t\t\tlistobjin:$here,visible+listable", b)


class TestUnlockableExitsStayHidden(unittest.TestCase):
    """A secret passage shouldn't be advertised before it's found."""

    @classmethod
    def setUpClass(cls):
        g = game(responses=[{"command": "USE KEY", "condition": "HAS KEY",
                             "message": "CLICK", "action": "UNLOCK EAST 1 TO 3"}])
        cls.block = room_block(emit(g), "room1")

    def test_the_locked_direction_is_absent_until_unlocked(self):
        self.assertIn("\t\t\tmsg:EXITS: SOUTH", self.block)

    def test_it_appears_once_the_unlock_variable_is_set(self):
        self.assertIn("\t\t\tmsg:EXITS: SOUTH, EAST", self.block)

    def test_the_two_are_branches_of_the_unlock_variable(self):
        uv = ed.unlock_var("1", "EAST")
        self.assertIn(f"\t\tif:{uv}=1", self.block)
        self.assertIn("\t\telse", self.block)


class TestVocabularyReachesTheGraphicalTarget(unittest.TestCase):
    """The synonym list was dropped whenever stdlib already knew the verb,
    so EXAMINE=X,INSPECT,SEARCH gave only the two words stdlib defines."""

    @classmethod
    def setUpClass(cls):
        cls.script = emit(game(
            vocabulary={"EXAMINE": ["X", "INSPECT", "SEARCH"],
                        "TAKE": ["GET", "GRAB"]},
            responses=[{"command": "EXAMINE KEY", "condition": "",
                        "message": "SHINY", "action": ""}]))

    def test_a_stdlib_verb_still_gets_the_authors_words(self):
        self.assertIn("verb:x", self.script.splitlines())
        syn = [l for l in self.script.splitlines() if l.startswith("\tsyn:x,")]
        self.assertTrue(syn, "no syn line for the x verb")
        for w in ("inspect", "search"):
            self.assertIn(w, syn[0])

    def test_a_verb_no_response_uses_is_still_declared(self):
        # TAKE is stdlib's, and no response uses it, but GRAB is the
        # author's word and has to reach the parser
        syn = [l for l in self.script.splitlines()
               if l.startswith("\tsyn:take,")]
        self.assertTrue(syn, "no syn line for the take verb")
        self.assertIn("grab", syn[0])


class TestASynonymCanStartACommand(unittest.TestCase):
    """'INSPECT BOOKCASE' used to declare a separate 'inspect' verb instead
    of routing to EXAMINE, so the two spellings ran different code."""

    @classmethod
    def setUpClass(cls):
        cls.conv = ed.Converter(game(
            vocabulary={"EXAMINE": ["X", "INSPECT"]},
            responses=[{"command": "INSPECT KEY", "condition": "",
                        "message": "SHINY", "action": ""}]))
        cls.script = cls.conv.emit()

    def test_it_maps_to_the_canonical_verb(self):
        self.assertEqual(self.conv.canonical_verb("INSPECT"), "x")

    def test_no_duplicate_verb_is_declared(self):
        self.assertNotIn("verb:inspect", self.script.splitlines())

    def test_the_response_hangs_off_the_canonical_verb(self):
        self.assertIn(("key", "x"), self.conv.groups)


class TestDirectionWordsAreVerbs(unittest.TestCase):
    """NORTH is stdlib's 'n'; without the mapping every direction entry in
    the Vocabulary tab was reported as 'not a verb'."""

    def test_north_maps_to_the_stdlib_short_form(self):
        c = ed.Converter(game(vocabulary={"NORTH": ["N"]}))
        self.assertEqual(c.canonical_verb("NORTH"), "n")

    def test_it_does_not_warn(self):
        c = ed.Converter(game(vocabulary={"NORTH": ["N"], "WEST": ["W"]}))
        c.emit()
        self.assertEqual([w for w in c.warnings if "Vocabulary" in w], [])


class TestANonVerbEntryIsReported(unittest.TestCase):
    """Declaring a noun as a verb would shadow the object it names."""

    @classmethod
    def setUpClass(cls):
        cls.conv = ed.Converter(game(vocabulary={"CHALICE": ["CUP", "GOBLET"]}))
        cls.script = cls.conv.emit()

    def test_it_is_not_declared_as_a_verb(self):
        self.assertNotIn("verb:chalice", self.script.splitlines())

    def test_the_author_is_told_why(self):
        self.assertTrue(any("CHALICE" in w and "isn't a verb" in w
                            for w in self.conv.warnings))



class TestASynonymAloneKeepsTheEntry(unittest.TestCase):
    """HIT=SLASH,KILL is a real verb even if every response is written
    'SLASH BEAST' - the base word never appearing isn't a reason to drop it."""

    @classmethod
    def setUpClass(cls):
        cls.conv = ed.Converter(game(
            vocabulary={"HIT": ["SLASH", "KILL"]},
            responses=[{"command": "SLASH KEY", "condition": "",
                        "message": "CLANG", "action": ""}]))
        cls.script = cls.conv.emit()

    def test_it_is_not_reported_as_a_non_verb(self):
        self.assertEqual([w for w in self.conv.warnings if "isn't a verb" in w],
                         [])

    def test_all_three_words_are_declared(self):
        syn = [l for l in self.script.splitlines() if l.startswith("\tsyn:hit,")]
        self.assertTrue(syn, "no syn line for the hit verb")
        for w in ("slash", "kill"):
            self.assertIn(w, syn[0])


if __name__ == "__main__":
    unittest.main()
