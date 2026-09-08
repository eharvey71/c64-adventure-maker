"""Headless smoke test for the editor UI.

Runs only where Tkinter and a display are available (CI provides one via
Xvfb). It does not judge whether artwork is framed well — that needs human
eyes on a real C64 — but it does prove the editor builds its tabs and that
the crop control reads, writes, and re-renders.
"""
import base64
import os
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

import adventure_editor_v7 as ed  # noqa: E402

try:
    import tkinter as tk
    _NO_TK = None
except ImportError as exc:      # pragma: no cover
    tk, _NO_TK = None, str(exc)


def has_display():
    return bool(os.environ.get("DISPLAY") or sys.platform in ("darwin", "win32"))


@unittest.skipIf(tk is None, f"Tkinter unavailable: {_NO_TK}")
@unittest.skipUnless(has_display(), "no display available")
class TestEditorSmoke(unittest.TestCase):
    def setUp(self):
        try:
            self.root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(f"cannot open display: {exc}")
        self.root.withdraw()
        self.app = ed.AdventureEditor(self.root)
        self.root.update()

    def tearDown(self):
        self.root.destroy()

    def add_scene(self, sid="ART", crop=None):
        scene = {"name": sid, "koala_b64": base64.b64encode(bytes(10001)).decode()}
        if crop is not None:
            scene["crop_offset"] = crop
        self.app.game.setdefault("scenes", {})[sid] = scene
        self.app.refresh_scenes_list()
        self.app.scenes_listbox.selection_clear(0, tk.END)
        for i in range(self.app.scenes_listbox.size()):
            if self.app.scenes_listbox.get(i).split(":", 1)[0].strip() == sid:
                self.app.scenes_listbox.selection_set(i)
                break
        self.app.on_scene_selected(None)
        self.root.update()

    def test_editor_builds(self):
        self.assertIsNotNone(self.app.scenes_listbox)
        self.assertIsNotNone(self.app.scene_crop_scale)

    def test_selecting_a_scene_loads_its_crop(self):
        self.add_scene(crop=104)
        self.assertEqual(self.app.scene_crop_var.get(), 104)
        self.assertIn("104", self.app.scene_crop_label_var.get())

    def test_moving_the_slider_stores_the_offset(self):
        self.add_scene(crop=0)
        self.app.on_scene_crop_changed(100)
        self.root.update()
        self.assertEqual(self.app.game["scenes"]["ART"]["crop_offset"], 96)

    def test_slider_snaps_to_cell_alignment(self):
        self.add_scene(crop=0)
        for raw in (5, 13.4, 51.9, 99):
            self.app.on_scene_crop_changed(raw)
            self.assertEqual(
                self.app.game["scenes"]["ART"]["crop_offset"] % ed.CROP_STEP, 0)

    def test_center_button_centers_the_band(self):
        self.add_scene(crop=0)
        self.app.center_scene_crop()
        self.root.update()
        self.assertEqual(self.app.game["scenes"]["ART"]["crop_offset"],
                         ed.CROP_CENTERED)

    def test_preview_renders(self):
        self.add_scene(crop=48)
        self.assertIsNotNone(self.app._scene_preview_photo)

    def test_crop_is_per_scene(self):
        self.add_scene("A", crop=0)
        self.add_scene("B", crop=104)
        self.assertEqual(self.app.game["scenes"]["A"]["crop_offset"], 0)
        self.assertEqual(self.app.game["scenes"]["B"]["crop_offset"], 104)

    def test_crop_survives_a_save_load_round_trip(self):
        import json
        import tempfile
        self.add_scene(crop=104)
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "g.json"
            p.write_text(json.dumps(self.app.game))
            reloaded = json.loads(p.read_text())
        self.assertEqual(reloaded["scenes"]["ART"]["crop_offset"], 104)

    def test_responses_gutter_has_one_mark_per_row(self):
        self.app.responses_text.delete("1.0", tk.END)
        self.app.responses_text.insert("1.0",
            "USE LAMP::RUBBED.:\n"
            "EXAMINE LAMP::A LAMP.:\n"
            "USE COIN::SPENT.:SCORE 10\n")
        self.app.on_responses_changed()
        self.root.update()
        gutter = self.app.responses_gutter.get("1.0", tk.END).rstrip("\n").split("\n")
        self.assertEqual(gutter[:3], ["both", "both", "both"])

    def test_responses_gutter_updates_as_you_type(self):
        self.app.responses_text.delete("1.0", tk.END)
        self.app.responses_text.insert("1.0", "USE LAMP::RUBBED.:\n")
        self.app.on_responses_changed(); self.root.update()
        self.assertEqual(
            self.app.responses_gutter.get("1.0", "1.end"), "both")
        self.app.responses_text.delete("1.0", tk.END)
        self.app.responses_text.insert("1.0", "USE LAMP::HELLO.:TELEPORT 4\n")
        self.app.on_responses_changed(); self.root.update()
        self.assertEqual(
            self.app.responses_gutter.get("1.0", "1.end"), "graphics only")

    def test_responses_detail_lists_reasons_by_line(self):
        self.app.responses_text.delete("1.0", tk.END)
        self.app.responses_text.insert("1.0", "USE WAND:WEATHER SUNNY::TELEPORT 4\n")
        self.app.on_responses_changed(); self.root.update()
        body = self.app.responses_detail.get("1.0", tk.END)
        self.assertIn("Line 1:", body)
        self.assertIn("WEATHER SUNNY", body)
        self.assertIn("TELEPORT", body)

    def test_responses_gutter_is_read_only(self):
        self.assertEqual(str(self.app.responses_gutter.cget("state")), "disabled")

    def test_empty_responses_do_not_crash_the_gutter(self):
        self.app.responses_text.delete("1.0", tk.END)
        self.app.on_responses_changed()
        self.root.update()

    def test_win_message_field_is_populated_from_a_loaded_game(self):
        import json
        with open(REPO / "example_castle.json") as f:
            game = json.load(f)
        game["messages"]["WIN_GAME"] = "THE CROWN IS YOURS!"
        self.app.game = game
        self.app.refresh_all()
        self.root.update()
        self.assertEqual(self.app.winmessage_var.get(), "THE CROWN IS YOURS!")

    def test_loading_migrates_the_old_system_messages_away(self):
        import json
        with open(REPO / "example_castle.json") as f:
            game = json.load(f)
        game["messages"]["CANT_GO"] = "MY WALL TEXT."
        self.app.game = game
        self.app.refresh_all()
        self.root.update()
        self.assertNotIn("CANT_GO", self.app.game["messages"])
        self.assertIn("WIZARD_GREETING", self.app.game["messages"])

    def test_the_system_message_section_is_gone(self):
        self.assertFalse(hasattr(self.app, "_sys_msg_vars"))

    def test_reasons_panel_scrolls_when_it_overflows(self):
        rows = "\n".join(f"USE T{i}:WEATHER SUNNY::TELEPORT {i}"
                         for i in range(1, 13))
        self.app.responses_text.delete("1.0", tk.END)
        self.app.responses_text.insert("1.0", rows + "\n")
        self.app.on_responses_changed()
        self.root.update()
        body = self.app.responses_detail.get("1.0", tk.END)
        reasons = [l for l in body.split("\n") if l.startswith("Line ")]
        # well past the panel's six visible lines; the exact count depends on
        # how many notes each row earns, which is not what this test is about
        self.assertGreater(len(reasons),
                           int(self.app.responses_detail.cget("height")))
        first, last = self.app.responses_detail_scroll.get()
        self.assertLess(last - first, 1.0, "panel reports no scrollable range")

    def test_reasons_panel_scrollbar_is_wired_both_ways(self):
        self.assertEqual(
            str(self.app.responses_detail.cget("yscrollcommand")).strip() != "", True)
        self.assertEqual(
            str(self.app.responses_detail_scroll.cget("command")).strip() != "", True)

    def test_reasons_panel_returns_to_the_top_after_an_edit(self):
        rows = "\n".join(f"USE T{i}:WEATHER SUNNY::TELEPORT {i}"
                         for i in range(1, 13))
        self.app.responses_text.delete("1.0", tk.END)
        self.app.responses_text.insert("1.0", rows + "\n")
        self.app.on_responses_changed(); self.root.update()
        self.app.responses_detail.yview_moveto(1.0); self.root.update()
        self.app.on_responses_changed(); self.root.update()
        self.assertEqual(self.app.responses_detail_scroll.get()[0], 0.0)

    def test_every_limit_has_a_visible_counter(self):
        import adventure_editor_v7 as ed
        self.assertEqual(set(self.app._capacity_vars), set(ed.BASIC_LIMITS))

    def test_counters_reflect_a_loaded_game(self):
        import json
        with open(REPO / "example_castle.json") as f:
            self.app.game = json.load(f)
        self.app.refresh_all(); self.root.update()
        self.assertIn("8 of 20 rooms", self.app._capacity_vars["rooms"].get())
        self.assertIn("11 of 20 responses",
                      self.app._capacity_vars["responses"].get())

    def test_counters_update_when_responses_overflow(self):
        rows = "\n".join(f"USE T{i}::M{i}.:" for i in range(1, 26))
        self.app.responses_text.delete("1.0", tk.END)
        self.app.responses_text.insert("1.0", rows + "\n")
        self.app.on_responses_changed(); self.root.update()
        text = self.app._capacity_vars["responses"].get()
        self.assertIn("stops at 20", text)
        self.assertIn("last 5", text)

    def test_flag_counter_tracks_the_responses(self):
        self.app.responses_text.delete("1.0", tk.END)
        self.app.responses_text.insert(
            "1.0", "USE A::X.:SET FLAG.ONE\nUSE B:NOT FLAG.TWO:Y.:\n")
        self.app.on_responses_changed(); self.root.update()
        self.assertIn("2 of 10 flags", self.app._capacity_vars["flags"].get())

    def test_a_letter_in_an_exit_field_does_not_crash(self):
        import json
        with open(REPO / "example_castle.json") as f:
            self.app.game = json.load(f)
        self.app.refresh_all()
        self.app.select_room_in_editor("2")
        self.root.update()
        before = list(self.app.game["rooms"]["2"]["exits"])
        for bad in ("E", "north", "-", "  ", "12a"):
            self.app.room_exit_e.set(bad)
            self.root.update()
            self.assertEqual(self.app.game["rooms"]["2"]["exits"], before,
                             f"{bad!r} changed the stored exits")

    def test_a_valid_exit_still_applies(self):
        import json
        with open(REPO / "example_castle.json") as f:
            self.app.game = json.load(f)
        self.app.refresh_all()
        self.app.select_room_in_editor("2")
        self.root.update()
        self.app.room_exit_e.set("9")
        self.root.update()
        self.assertEqual(self.app.game["rooms"]["2"]["exits"][2], 9)

    def test_both_disk_builds_are_on_the_file_menu(self):
        menu = self.root.nametowidget(self.root.cget("menu"))
        file_menu = menu.nametowidget(menu.entrycget(0, "menu"))
        labels = [file_menu.entrycget(i, "label")
                  for i in range(file_menu.index("end") + 1)
                  if file_menu.type(i) == "command"]
        self.assertTrue(any("graphical" in l for l in labels), labels)
        self.assertTrue(any("text only" in l for l in labels), labels)

    def test_the_text_build_entry_point_exists(self):
        self.assertTrue(callable(self.app.export_and_build_text))

    def test_crop_control_with_no_scene_selected_does_not_crash(self):
        self.app._current_scene_id = None
        self.app.on_scene_crop_changed(48)   # must be a no-op, not an error


if __name__ == "__main__":
    unittest.main()
