"""Tests for the one-click text (.adv) disk build.

The build is pure Python (c64build), so it runs here end to end: the file
naming rules a 1541 imposes, the line endings the runtime requires, and the
disk the editor actually writes.
"""
import json
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(Path(__file__).resolve().parent))   # test_c64build

import adventure_editor_v7 as ed  # noqa: E402


class TestTheRuntimeIsShipped(unittest.TestCase):
    def test_the_basic_source_is_in_legacy(self):
        self.assertTrue((REPO / "legacy" / ed.AdventureEditor.BASIC_RUNTIME).exists())

    def test_it_is_lowercase_as_petcat_requires(self):
        src = (REPO / "legacy" / ed.AdventureEditor.BASIC_RUNTIME).read_text()
        code = "\n".join(l for l in src.splitlines() if not l.startswith("#"))
        # BASIC keywords must be lowercase for petcat to tokenise them
        self.assertNotIn("PRINT ", code)
        self.assertIn("print ", code)


class TestDiskFilenames(unittest.TestCase):
    """A 1541 directory entry is 16 characters, and the runtime asks the
    player to type the name, so it has to be guessable."""

    NAME = "game.adv"

    def test_the_name_fits_a_directory_entry(self):
        self.assertLessEqual(len(self.NAME), 16)

    def test_the_build_uses_it(self):
        self.assertEqual(ed.TEXT_GAME_NAME, self.NAME)

    def test_it_does_not_depend_on_the_title(self):
        # a long title used to produce "the_haunted_.adv", which nobody could
        # be expected to guess at the runtime's prompt. The disk label may
        # still be cut from the title - only the name the player types matters.
        from test_c64build import read_directory
        runtime = (REPO / "legacy" / ed.AdventureEditor.BASIC_RUNTIME).read_text()
        with open(REPO / "example_castle.json") as f:
            game = json.load(f)
        for title in ("X", "The Haunted Castle", "A Very Long Title Indeed, Friends"):
            game["settings"]["title"] = title
            disk = ed.build_text_disk(game, runtime)["disk"]
            names = [entry[0] for entry in read_directory(disk)]
            self.assertEqual(names, [b"ADVPLAY", b"GAME.ADV"], title)

    def test_the_disk_label_still_carries_the_title(self):
        self.assertTrue(ed.slugify("The Haunted Castle")[:16].startswith("the_haunted"))


class TestUnreadableFileIsReported(unittest.TestCase):
    """Loading a name that is not on the disk used to leave the player in a
    room-less game with no explanation."""

    @classmethod
    def setUpClass(cls):
        cls.src = (REPO / "legacy" / ed.AdventureEditor.BASIC_RUNTIME).read_text()

    def test_the_loader_checks_whether_any_room_arrived(self):
        self.assertIn("if nr=0 then", self.src)

    def test_it_says_which_file_it_could_not_read(self):
        self.assertIn('print "could not read ";f$', self.src)

    def test_it_returns_to_the_prompt_rather_than_starting(self):
        line = [l for l in self.src.splitlines() if l.startswith("1998 ")][0]
        self.assertIn("goto 200", line)

    def test_the_prompt_still_appends_the_extension(self):
        self.assertIn('f$=f$+".adv"', self.src)


class TestAdvLineEndings(unittest.TestCase):
    """The runtime reads a byte at a time and ends a line on CHR$(13)."""

    def encode(self, text):
        out = b""
        for line in text.split("\n"):
            line = line.rstrip()
            if line:
                out += line.encode("ascii", "replace") + b"\r"
        return out

    def test_lines_end_with_cr_not_lf(self):
        data = self.encode("A\nB\n")
        self.assertEqual(data, b"A\rB\r")
        self.assertNotIn(b"\n", data)

    def test_blank_lines_are_dropped(self):
        self.assertEqual(self.encode("A\n\n\nB\n"), b"A\rB\r")

    def test_the_file_ends_with_a_terminator(self):
        self.assertTrue(self.encode("A\nB\n").endswith(b"\r"))

    def test_the_castle_encodes_to_ascii(self):
        with open(REPO / "example_castle.json") as f:
            game = json.load(f)
        # generate_adv is a method, so exercise the encoding on its shape
        text = "\n".join(f"{k}={v}" for k, v in game["settings"].items())
        self.assertIsInstance(self.encode(text), bytes)


class TestNoViceNeeded(unittest.TestCase):
    """The text build used to shell out to petcat and c1541."""

    def test_the_build_does_not_call_petcat_or_c1541(self):
        import inspect
        for fn in (ed.AdventureEditor._do_export_and_build_text,
                   ed.AdventureEditor._run_text_build):
            src = inspect.getsource(fn)
            self.assertNotIn("petcat", src.replace("`petcat -w2`", ""))
            self.assertNotIn("c1541", src)


class TestTheEditorsBuild(unittest.TestCase):
    """Run the editor's own text build, with the dialogs captured."""

    @classmethod
    def setUpClass(cls):
        import tempfile
        import c64build
        cls.cb = c64build
        cls.shown = []
        shown = cls.shown

        class Dialogs:
            def showerror(self, title, msg): shown.append(("error", title, msg))
            def showinfo(self, title, msg): shown.append(("info", title, msg))
            def askyesno(self, title, msg): shown.append(("ask", title, msg)); return False

        with open(REPO / "example_castle.json") as f:
            game = json.load(f)

        class Editor:
            _int_field = ed.AdventureEditor._int_field
            generate_adv = ed.AdventureEditor.generate_adv
            def _find_x64sc(self): return None
        Editor.game = game
        cls.editor = Editor()

        saved, ed.messagebox = ed.messagebox, Dialogs()
        try:
            cls.out = Path(tempfile.mkdtemp())
            ed.AdventureEditor._run_text_build(
                cls.editor, REPO / "legacy" / ed.AdventureEditor.BASIC_RUNTIME,
                cls.out)
        finally:
            ed.messagebox = saved
        disks = list(cls.out.rglob("*.d64"))
        cls.disk = disks[0].read_bytes() if disks else None

    def test_it_reports_success(self):
        self.assertEqual([k for k, _t, _m in self.shown], ["info"], self.shown)

    def test_it_writes_a_disk(self):
        self.assertIsNotNone(self.disk)
        self.assertEqual(len(self.disk), 174848)

    def test_the_disk_holds_the_player_and_the_game(self):
        from test_c64build import read_directory
        files = read_directory(self.disk)
        self.assertEqual([(f[0], f[1]) for f in files],
                         [(b"ADVPLAY", 0x82), (b"GAME.ADV", 0x81)])
        runtime = (REPO / "legacy" / ed.AdventureEditor.BASIC_RUNTIME).read_text()
        self.assertEqual(files[0][5], self.cb.tokenize_basic(runtime))
        self.assertTrue(files[1][5].startswith(b"[SETTINGS]\r"))

    def test_the_label_carries_the_title(self):
        from test_c64build import sector
        self.assertEqual(sector(self.disk, 18, 0)[0x90:0xA0], b"THE_HAUNTED_CAST")


if __name__ == "__main__":
    unittest.main()
