"""Tests for the one-click graphical (StoryTllr) disk build.

The disk is written by c64build rather than VICE's c1541. The end-to-end
test needs tools/script_compiler (built by tools/setup_compiler.sh) and
skips without it; CI builds it on Linux.
"""
import inspect
import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(Path(__file__).resolve().parent))   # test_c64build

import adventure_editor_v7 as ed  # noqa: E402
from test_c64build import read_directory, sector  # noqa: E402

COMPILER = REPO / "tools" / "script_compiler"


class TestNoViceNeeded(unittest.TestCase):
    def test_the_build_does_not_call_c1541(self):
        for fn in (ed.AdventureEditor._do_export_and_build,
                   ed.AdventureEditor._run_build):
            code = "\n".join(l for l in inspect.getsource(fn).splitlines()
                             if not l.strip().startswith("#"))
            self.assertNotIn("c1541", code)

    def test_the_editor_no_longer_looks_for_c1541(self):
        self.assertFalse(hasattr(ed.AdventureEditor, "_find_c1541"))


@unittest.skipUnless(COMPILER.exists(), "tools/script_compiler not built")
class TestTheEditorsBuild(unittest.TestCase):
    """Run the editor's own graphical build, with the dialogs captured."""

    @classmethod
    def setUpClass(cls):
        cls.shown = []
        shown = cls.shown

        class Dialogs:
            def showerror(self, title, msg): shown.append(("error", title, msg))
            def showinfo(self, title, msg): shown.append(("info", title, msg))
            def askyesno(self, title, msg): shown.append(("ask", title, msg)); return False

        with open(REPO / "example_castle.json") as f:
            cls.game = json.load(f)

        class Editor:
            def _kit_engine_file(self, name):
                p = REPO / "engine" / name
                return p if p.exists() else None
            def _find_x64sc(self): return None
        Editor.game = cls.game

        saved, ed.messagebox = ed.messagebox, Dialogs()
        try:
            out = Path(tempfile.mkdtemp())
            conv = ed.Converter(cls.game, crop_offset=ed.STORYTLLR_CROP_OFFSET)
            ed.AdventureEditor._run_build(Editor(), conv, str(COMPILER), out)
        finally:
            ed.messagebox = saved
        disks = list(out.rglob("*.d64"))
        cls.disk = disks[0].read_bytes() if disks else None

    def test_it_reports_success(self):
        self.assertEqual([k for k, _t, _m in self.shown], ["info"], self.shown)

    def test_the_disk_holds_player_font_game_and_every_room(self):
        files = read_directory(self.disk)
        names = [f[0] for f in files]
        rooms = sorted(f"ROOM{int(r):02d}".encode() for r in self.game["rooms"])
        self.assertEqual(names, [b"THE_HAUNTED_CAST", b"FONT", b"ADVCARTRIDGE"] + rooms)
        self.assertTrue(all(f[1] == 0x82 for f in files), "all PRG")

    def test_the_player_is_the_engine_unchanged(self):
        player = read_directory(self.disk)[0][5]
        self.assertEqual(player, (REPO / "engine" / "storytllr64.prg").read_bytes())

    def test_the_disk_id_is_66(self):
        self.assertEqual(sector(self.disk, 18, 0)[0xA2:0xA4], b"66")


if __name__ == "__main__":
    unittest.main()
