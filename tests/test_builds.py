"""Tests for the shared build functions the desktop and web versions call.

The graphical build takes the compiler as a function, so a fake one stands
in here: these run everywhere, with no compiler built. tests/test_graphical_
build.py runs the real one through the desktop editor.
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(Path(__file__).resolve().parent))   # test_c64build

import adventure_editor_v7 as ed  # noqa: E402
import c64build  # noqa: E402
from test_c64build import read_directory, sector  # noqa: E402

RUNTIME = (REPO / "legacy" / ed.AdventureEditor.BASIC_RUNTIME).read_text()
ENGINE = REPO / "engine"


def castle():
    with open(REPO / "example_castle.json") as f:
        return json.load(f)


class TestTextBuild(unittest.TestCase):
    def setUp(self):
        self.built = ed.build_text_disk(castle(), RUNTIME)

    def test_it_returns_the_disk_and_its_pieces(self):
        self.assertEqual(set(self.built), {"disk", "prg", "adv"})

    def test_the_disk_holds_exactly_those_pieces(self):
        files = read_directory(self.built["disk"])
        self.assertEqual(files[0][5], self.built["prg"])
        self.assertEqual(files[1][5], self.built["adv"])

    def test_the_player_is_the_tokenised_runtime(self):
        self.assertEqual(self.built["prg"], c64build.tokenize_basic(RUNTIME))

    def test_the_game_uses_cr_line_endings_and_no_blank_lines(self):
        adv = self.built["adv"]
        self.assertNotIn(b"\n", adv)
        self.assertNotIn(b"\r\r", adv)
        self.assertTrue(adv.endswith(b"\r"))

    def test_the_game_is_the_editors_adv_text(self):
        text = ed.generate_adv(castle())
        lines = [l.rstrip() for l in text.split("\n") if l.rstrip()]
        self.assertEqual(self.built["adv"].decode("ascii").split("\r")[:-1], lines)

    def test_the_editor_method_delegates(self):
        class Editor:
            generate_adv = ed.AdventureEditor.generate_adv
        e = Editor()
        e.game = castle()
        self.assertEqual(e.generate_adv(), ed.generate_adv(castle()))

    def test_a_bad_runtime_raises(self):
        with self.assertRaises(c64build.BasicError):
            ed.build_text_disk(castle(), "print 1\n")


class FakeCompiler:
    """Writes what script_compiler writes, or prints what it prints."""

    def __init__(self, output="Done.", writes=True):
        self.output, self.writes, self.calls = output, writes, []

    def __call__(self, proj_dir, script):
        self.calls.append((proj_dir, script))
        proj = Path(proj_dir)
        if self.writes:
            (proj / "advcartridge").write_bytes(b"CART" * 100)
            (proj / "img" / "font").write_bytes(b"FONT" * 100)
            for png in sorted((proj / "png").glob("room*_C64.png")):
                name = png.name.split("_")[0]
                (proj / "img" / name).write_bytes(name.encode() * 50)
        return self.output


class TestGraphicalBuild(unittest.TestCase):
    def build(self, compiler, game=None):
        self.proj = Path(tempfile.mkdtemp()) / "proj"
        return ed.build_graphical_disk(
            game or castle(), self.proj, compiler, ENGINE / "stdlib.hjt",
            (ENGINE / "storytllr64.prg").read_bytes(),
            font_png=ENGINE / "font.png")

    def test_the_compiler_is_called_once_on_the_script(self):
        fake = FakeCompiler()
        self.build(fake)
        self.assertEqual(fake.calls, [(str(self.proj), "the_haunted_castle.hjt")])

    def test_the_project_holds_the_compilers_inputs(self):
        self.build(FakeCompiler())
        for name in ("the_haunted_castle.hjt", "stdlib.hjt", "png/font.png",
                     "png/room01_C64.png"):
            self.assertTrue((self.proj / name).exists(), name)

    def test_the_disk_holds_player_font_game_and_rooms(self):
        disk = self.build(FakeCompiler())
        files = read_directory(disk)
        rooms = sorted(f"ROOM{int(r):02d}".encode() for r in castle()["rooms"])
        self.assertEqual([f[0] for f in files],
                         [b"THE_HAUNTED_CAST", b"FONT", b"ADVCARTRIDGE"] + rooms)
        self.assertEqual(files[0][5], (ENGINE / "storytllr64.prg").read_bytes())
        self.assertEqual(files[2][5], b"CART" * 100)
        self.assertEqual(sector(disk, 18, 0)[0xA2:0xA4], b"66")

    def test_compiler_errors_are_raised_with_their_lines(self):
        fake = FakeCompiler(output="ROOMS: 10\nERR: verb :: frobnicate\nDone.")
        with self.assertRaises(ed.CompileError) as cm:
            self.build(fake)
        self.assertEqual(cm.exception.errors, ["ERR: verb :: frobnicate"])

    def test_no_game_written_is_an_error_too(self):
        with self.assertRaises(ed.CompileError):
            self.build(FakeCompiler(writes=False))

    def test_the_output_may_come_back_as_any_text_like_object(self):
        # the web page's compiler is JavaScript; Pyodide hands its string over
        class JsString:
            def __str__(self):
                return "Done."
        self.build(FakeCompiler(output=JsString()))


if __name__ == "__main__":
    unittest.main()
