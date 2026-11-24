"""add_koala_scene: how a Koala file becomes a scene, in both editors."""
import base64
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import adventure_editor_v7 as ed  # noqa: E402

KOALA = bytes(range(256)) * 39 + bytes(17)          # 10001 bytes
WITH_LOAD_ADDRESS = b"\x00\x60" + KOALA             # 10003 bytes


class TestAddKoalaScene(unittest.TestCase):
    def test_the_id_comes_from_the_file_name_in_capitals(self):
        game = {}
        sid = ed.add_koala_scene(game, "/some/where/Tower-Top.kla", KOALA)
        self.assertEqual(sid, "TOWERTOP")
        self.assertEqual(game["scenes"][sid]["name"], "Tower-Top")

    def test_a_second_import_of_the_same_name_gets_a_new_id(self):
        game = {}
        ed.add_koala_scene(game, "tower.kla", KOALA)
        self.assertEqual(ed.add_koala_scene(game, "tower.kla", KOALA), "TOWER_2")
        self.assertEqual(ed.add_koala_scene(game, "tower.kla", KOALA), "TOWER_3")

    def test_the_load_address_is_dropped(self):
        game = {}
        sid = ed.add_koala_scene(game, "a.kla", WITH_LOAD_ADDRESS)
        self.assertEqual(base64.b64decode(game["scenes"][sid]["koala_b64"]), KOALA)

    def test_the_visible_band_starts_centred(self):
        game = {}
        sid = ed.add_koala_scene(game, "a.kla", KOALA)
        self.assertEqual(game["scenes"][sid]["crop_offset"], ed.CROP_CENTERED)

    def test_a_name_with_no_letters_or_digits_becomes_scene(self):
        self.assertEqual(ed.add_koala_scene({}, "---.kla", KOALA), "SCENE")

    def test_a_file_that_isnt_koala_is_refused_and_nothing_is_added(self):
        game = {}
        with self.assertRaises(ValueError):
            ed.add_koala_scene(game, "photo.png", b"\x89PNG" + bytes(500))
        self.assertEqual(game.get("scenes", {}), {})


if __name__ == "__main__":
    unittest.main()
