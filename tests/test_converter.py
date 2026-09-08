"""Golden-file and unit tests for the JSON -> StoryTllr script converter.

The converter is pure (game dict in, script text out), so a golden file
pinned to example_castle.json catches any accidental change in the emitted
script. Regenerate deliberately with:

    python3 tests/update_golden.py
"""
import json
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

import adventure_editor_v7 as ed  # noqa: E402

GOLDEN = Path(__file__).parent / "golden" / "example_castle.hjt"
SAMPLE = REPO / "example_castle.json"


def load_sample():
    with open(SAMPLE) as f:
        return json.load(f)


def convert(game):
    return ed.Converter(game, crop_offset=ed.STORYTLLR_CROP_OFFSET).emit()


class TestGoldenOutput(unittest.TestCase):
    def test_example_castle_matches_golden(self):
        actual = convert(load_sample())
        expected = GOLDEN.read_text()
        if actual != expected:
            import difflib
            diff = "\n".join(difflib.unified_diff(
                expected.splitlines(), actual.splitlines(),
                "golden", "actual", lineterm=""))
            self.fail("converter output changed:\n" + diff)

    def test_output_is_deterministic(self):
        self.assertEqual(convert(load_sample()), convert(load_sample()))


class TestScriptShape(unittest.TestCase):
    """Invariants the StoryTllr compiler and C64 player depend on."""

    @classmethod
    def setUpClass(cls):
        cls.text = convert(load_sample())
        cls.lines = cls.text.splitlines()

    def test_starts_with_config_block(self):
        self.assertEqual(self.lines[0], "config")

    def test_includes_stdlib(self):
        self.assertIn("include:stdlib.hjt", self.lines)

    def test_indentation_is_tabs_only(self):
        for i, line in enumerate(self.lines, 1):
            indent = line[:len(line) - len(line.lstrip())]
            self.assertNotIn(" ", indent, f"line {i} indented with spaces")

    def test_if_variable_names_are_pure_letters(self):
        # The compiler's ifget tokenizer stops at digits and underscores, so
        # a variable named e.g. `room1` or `has_key` silently misparses.
        for line in self.lines:
            body = line.strip()
            if not body.startswith("if:"):
                continue
            name = body[3:].split("=")[0].split("<")[0].split(">")[0]
            self.assertTrue(
                name.isalpha(),
                f"if: variable {name!r} must be pure letters, in {body!r}")

    def test_setvar_names_are_pure_letters(self):
        for line in self.lines:
            body = line.strip()
            if not body.startswith("setvar:"):
                continue
            name = body[len("setvar:"):].split(",")[0]
            self.assertTrue(
                name.isalpha(),
                f"setvar name {name!r} must be pure letters, in {body!r}")

    def test_every_room_declares_an_image(self):
        rooms = [l for l in self.lines if l.startswith("room:")]
        images = [l for l in self.lines if l.strip().startswith("image:")]
        self.assertTrue(rooms, "sample game should declare rooms")
        # one image per room, plus the start-room image in the start block
        self.assertGreaterEqual(len(images), len(rooms))

    def test_room_image_paths_use_backslash_and_two_digits(self):
        import re
        for line in self.lines:
            body = line.strip()
            if body.startswith("image:"):
                self.assertRegex(body, r"^image:png\\room\d{2}_C64\.png$")

    def test_no_blank_or_whitespace_only_lines(self):
        for i, line in enumerate(self.lines, 1):
            self.assertTrue(line.strip(), f"line {i} is blank")

    def test_branch_nesting_increases_by_one_tab(self):
        depth = lambda s: len(s) - len(s.lstrip("\t"))
        prev = 0
        for i, line in enumerate(self.lines, 1):
            d = depth(line)
            self.assertLessEqual(
                d, prev + 1, f"line {i} jumps more than one indent level")
            prev = d


class TestConverterUnits(unittest.TestCase):
    def test_slugify(self):
        self.assertEqual(ed.slugify("The Haunted Castle"), "the_haunted_castle")
        self.assertEqual(ed.slugify("a  --  b"), "a_b")
        self.assertEqual(ed.slugify(""), "game")

    def test_flag_var_is_pure_letters(self):
        for name in ("has_key", "door1open", "FLAG_2"):
            self.assertTrue(ed.flag_var(name).isalpha(),
                            f"flag_var({name!r}) must be pure letters")

    def test_flag_var_is_stable(self):
        self.assertEqual(ed.flag_var("has_key"), ed.flag_var("has_key"))

    def test_flag_var_distinguishes_names(self):
        self.assertNotEqual(ed.flag_var("door_a"), ed.flag_var("door_b"))

    def test_unlock_var_is_pure_letters(self):
        # Every direction the C64 export supports must yield an alpha-only
        # name, since the compiler's if: tokenizer rejects anything else.
        for room in ("1", "9", "27", "53"):
            for direction in ed.DIR_SHORT:
                self.assertTrue(
                    ed.unlock_var(room, direction).isalpha(),
                    f"unlock_var({room!r}, {direction!r}) not alpha")

    def test_unlock_vars_are_unique_per_room_and_direction(self):
        names = {ed.unlock_var(str(r), d)
                 for r in range(1, 30) for d in ed.DIR_SHORT}
        self.assertEqual(len(names), 29 * len(ed.DIR_SHORT))

    def test_dir_tables_stay_in_sync(self):
        self.assertEqual(len(ed.DIR_NAMES), len(ed.DIR_VERBS))
        self.assertEqual(set(ed.DIR_NAMES), set(ed.DIR_SHORT))

    def test_room_letters_round_trip_distinct(self):
        seen = {ed.room_letters(str(n)) for n in range(1, 40)}
        self.assertEqual(len(seen), 39, "room letter codes must be unique")

    def test_empty_game_converts(self):
        empty = {"settings": {}, "rooms": {}, "objects": {},
                 "vocabulary": {}, "messages": {}, "responses": []}
        text = convert(empty)
        self.assertTrue(text.startswith("config"))


class TestKoalaDecoder(unittest.TestCase):
    def test_strips_two_byte_load_address(self):
        raw = bytes([0x00, 0x60]) + bytes(10001)
        self.assertEqual(len(ed.strip_koala_load_address(raw)), 10001)

    def test_leaves_bare_image_alone(self):
        raw = bytes(10001)
        self.assertEqual(len(ed.strip_koala_load_address(raw)), 10001)

    def test_decodes_to_expected_pixel_grid(self):
        px, w, h = ed.decode_koala_to_rgb(bytes(10001))
        self.assertEqual((w, h), (160, 200))
        self.assertEqual(len(px), 160 * 200 * 3)

    def test_decodes_bit_pairs_to_the_right_palette_entries(self):
        # One cell (top-left), bitmap byte 0b00_01_10_11 -> bg, c01, c10, c11.
        data = bytearray(10001)
        data[0] = 0b00011011
        data[8000] = 0x12          # hi nibble = c01 (1), lo nibble = c10 (2)
        data[9000] = 0x03          # c11 = 3
        data[10000] = 0x05         # background = 5
        px, w, _ = ed.decode_koala_to_rgb(bytes(data))
        got = [tuple(px[i * 3:i * 3 + 3]) for i in range(4)]
        want = [ed.C64_PALETTE[i] for i in (5, 1, 2, 3)]
        self.assertEqual(got, want)

    def test_rejects_short_data(self):
        with self.assertRaises(Exception):
            ed.decode_koala_to_rgb(bytes(100))

    def test_palette_is_sixteen_rgb_triplets(self):
        self.assertEqual(len(ed.C64_PALETTE), 16)
        for c in ed.C64_PALETTE:
            self.assertEqual(len(c), 3)
            self.assertTrue(all(0 <= v <= 255 for v in c))


class TestPngWriter(unittest.TestCase):
    def test_writes_valid_png_signature_and_iend(self):
        import tempfile
        rows = [bytes([0, 0, 0] * 4) for _ in range(4)]
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "t.png"
            ed.write_png(str(p), 4, 4, rows)
            data = p.read_bytes()
        self.assertEqual(data[:8], b"\x89PNG\r\n\x1a\n")
        self.assertTrue(data.endswith(b"IEND\xaeB`\x82"))

    def test_placeholder_room_png_is_readable(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "room01.png"
            ed.placeholder_room_png(1, str(p))
            self.assertGreater(p.stat().st_size, 0)
            self.assertEqual(p.read_bytes()[:8], b"\x89PNG\r\n\x1a\n")


if __name__ == "__main__":
    unittest.main()


class TestTolerantNumericFields(unittest.TestCase):
    """Numeric entries are traced on every keystroke, so they get read
    mid-edit. None of these may raise."""

    parse = staticmethod(ed.AdventureEditor._int_field)

    def test_a_plain_number(self):
        self.assertEqual(self.parse("7", 1), 7)

    def test_whitespace_is_trimmed(self):
        self.assertEqual(self.parse("  7  ", 1), 7)

    def test_empty_falls_back(self):
        self.assertEqual(self.parse("", 4), 4)

    def test_whitespace_only_falls_back(self):
        self.assertEqual(self.parse("   ", 4), 4)

    def test_a_letter_falls_back(self):
        self.assertEqual(self.parse("E", 4), 4)

    def test_a_word_falls_back(self):
        self.assertEqual(self.parse("north", 4), 4)

    def test_a_partial_number_falls_back(self):
        self.assertEqual(self.parse("12a", 4), 4)

    def test_a_lone_minus_falls_back(self):
        self.assertEqual(self.parse("-", 4), 4)

    def test_a_negative_number_is_accepted(self):
        # -1 is how an object in the inventory is stored
        self.assertEqual(self.parse("-1", 4), -1)

    def test_none_falls_back(self):
        self.assertEqual(self.parse(None, 4), 4)
