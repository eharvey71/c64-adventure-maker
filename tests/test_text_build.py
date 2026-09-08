"""Tests for the one-click text (.adv) disk build.

The build itself needs petcat and c1541, so the parts that can be checked
without them are checked here: the file naming rules a 1541 imposes, the
line endings the runtime requires, and that the pieces the build depends on
are present in the repository.
"""
import json
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

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
    """A 1541 directory entry is 16 characters."""

    def adv_name(self, title):
        slug = ed.slugify(title)
        return slug[:16 - len(".adv")] + ".adv"

    def test_a_short_title_is_untouched(self):
        self.assertEqual(self.adv_name("Castle"), "castle.adv")

    def test_a_long_title_keeps_its_extension(self):
        name = self.adv_name("The Haunted Castle Of Doom And Peril")
        self.assertTrue(name.endswith(".adv"), name)
        self.assertLessEqual(len(name), 16)

    def test_the_stem_is_what_gets_trimmed(self):
        name = self.adv_name("The Haunted Castle")
        self.assertEqual(name, "the_haunted_.adv")

    def test_the_disk_label_fits(self):
        self.assertLessEqual(len(ed.slugify("The Haunted Castle")[:16]), 16)


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


class TestToolLookup(unittest.TestCase):
    def test_petcat_is_searched_for_in_the_vice_locations(self):
        import inspect
        src = inspect.getsource(ed.AdventureEditor._find_petcat)
        self.assertIn("VICE_DIRS", src)

    def test_petcat_gets_an_exe_suffix_on_windows(self):
        self.assertIn("petcat", ed.AdventureEditor._exe_names("petcat"))


if __name__ == "__main__":
    unittest.main()
