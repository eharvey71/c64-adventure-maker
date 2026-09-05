"""Contrast checks for the editor's dark theme.

These exist because ttk's `clam` theme ships light-grey defaults that are
inherited silently: the crop slider was rendering a #dcdad5 thumb on a
#bab5ab trough — a 1.5:1 ratio, effectively invisible. A widget that is
never explicitly styled looks fine to whoever wrote it and disappears for
someone else, so the ratios are asserted rather than eyeballed.

Thresholds follow WCAG 2.1:
  1.4.3  text and text-like elements   4.5:1
  1.4.11 non-text UI components/state  3.0:1

Contrast here is luminance-based, not hue-based, so it holds under any
form of color vision deficiency.
"""
import os
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

import adventure_editor_v7 as ed  # noqa: E402

try:
    import tkinter as tk
    from tkinter import ttk
    _NO_TK = None
except ImportError as exc:      # pragma: no cover
    tk = ttk = None
    _NO_TK = str(exc)

TEXT_MIN = 4.5
UI_MIN = 3.0


def relative_luminance(color):
    """WCAG relative luminance for a #rrggbb string."""
    h = color.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    channels = []
    for i in (0, 2, 4):
        v = int(h[i:i + 2], 16) / 255
        channels.append(v / 12.92 if v <= 0.04045
                        else ((v + 0.055) / 1.055) ** 2.4)
    r, g, b = channels
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(a, b):
    la, lb = relative_luminance(a), relative_luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


class TestContrastMath(unittest.TestCase):
    """Sanity-check the checker itself before trusting its verdicts."""

    def test_black_on_white_is_21(self):
        self.assertAlmostEqual(contrast_ratio("#000000", "#ffffff"), 21.0, places=1)

    def test_identical_colors_are_1(self):
        self.assertAlmostEqual(contrast_ratio("#3a3a40", "#3a3a40"), 1.0, places=3)

    def test_order_does_not_matter(self):
        self.assertAlmostEqual(contrast_ratio("#1c1c1e", "#d4d0c8"),
                               contrast_ratio("#d4d0c8", "#1c1c1e"), places=6)

    def test_shorthand_hex(self):
        self.assertAlmostEqual(contrast_ratio("#000", "#fff"), 21.0, places=1)

    def test_the_regression_this_file_exists_for(self):
        # clam's unstyled Scale: what the user could not see.
        self.assertLess(contrast_ratio("#dcdad5", "#bab5ab"), 1.6)


@unittest.skipIf(tk is None, f"Tkinter unavailable: {_NO_TK}")
@unittest.skipUnless(os.environ.get("DISPLAY") or sys.platform in ("darwin", "win32"),
                     "no display available")
class TestThemeContrast(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.root = tk.Tk()
        except tk.TclError as exc:
            raise unittest.SkipTest(f"cannot open display: {exc}")
        cls.root.withdraw()
        cls.app = ed.AdventureEditor(cls.root)
        cls.root.update()
        cls.style = ttk.Style()

    @classmethod
    def tearDownClass(cls):
        cls.root.destroy()

    def look(self, style_name, option):
        value = self.style.lookup(style_name, option)
        self.assertTrue(value, f"{style_name} has no {option} set")
        return value

    def assertContrast(self, a, b, minimum, label):
        r = contrast_ratio(a, b)
        self.assertGreaterEqual(
            r, minimum, f"{label}: {a} on {b} is {r:.2f}:1, need {minimum}:1")

    # -- the crop slider -------------------------------------------------
    def test_slider_thumb_against_trough(self):
        self.assertContrast(self.look("Band.Horizontal.TScale", "background"),
                            self.look("Band.Horizontal.TScale", "troughcolor"),
                            UI_MIN, "slider thumb vs trough")

    def test_slider_is_not_using_clam_defaults(self):
        for option, default in (("background", "#dcdad5"),
                                ("troughcolor", "#bab5ab")):
            self.assertNotEqual(
                self.look("Band.Horizontal.TScale", option).lower(), default,
                f"slider {option} fell back to the clam default")

    def test_slider_track_edge_is_visible(self):
        # The trough is near-black by design; its border is what delineates it.
        self.assertContrast(self.look("Band.Horizontal.TScale", "bordercolor"),
                            self.app.colors["bg_dark"], UI_MIN,
                            "slider track border vs page")

    def test_slider_is_actually_wired_to_the_style(self):
        self.assertEqual(str(self.app.scene_crop_scale.cget("style")),
                         "Band.Horizontal.TScale")

    # -- the room's scene picker -----------------------------------------
    def test_dropdown_text_against_fill(self):
        self.assertContrast(self.look("Picker.TMenubutton", "foreground"),
                            self.look("Picker.TMenubutton", "background"),
                            TEXT_MIN, "dropdown text vs fill")

    def test_dropdown_border_against_page(self):
        self.assertContrast(self.look("Picker.TMenubutton", "bordercolor"),
                            self.app.colors["bg_dark"], UI_MIN,
                            "dropdown border vs page")

    def test_dropdown_arrow_against_fill(self):
        self.assertContrast(self.look("Picker.TMenubutton", "arrowcolor"),
                            self.look("Picker.TMenubutton", "background"),
                            UI_MIN, "dropdown arrow vs fill")

    def test_dropdown_is_ttk_not_tk(self):
        # tk.Menubutton is ignored by macOS Aqua, which draws a native light
        # control instead; ttk under clam is drawn by Tk on every platform.
        self.assertIsInstance(self.app.room_scene_menubutton, ttk.Menubutton)

    # -- everything else that inherits the root style ---------------------
    def test_no_widget_inherits_a_light_bevel(self):
        for option in ("lightcolor", "darkcolor", "bordercolor"):
            value = self.style.lookup(".", option)
            if not value:
                continue
            self.assertLess(
                relative_luminance(value), 0.5,
                f"root style {option}={value} is a light bevel on a dark UI")

    def test_button_text_against_fill(self):
        self.assertContrast(self.look("TButton", "foreground"),
                            self.look("TButton", "background"),
                            TEXT_MIN, "button text vs fill")

    def test_body_text_against_page(self):
        self.assertContrast(self.app.colors["fg_primary"],
                            self.app.colors["bg_dark"],
                            TEXT_MIN, "body text vs page")

    def test_hint_text_against_panel(self):
        self.assertContrast(self.app.colors["fg_hint"],
                            self.app.colors["bg_mid"],
                            TEXT_MIN, "hint text vs panel")

    def test_crop_label_against_page(self):
        self.assertContrast(self.app.colors["fg_hint"],
                            self.app.colors["bg_dark"],
                            TEXT_MIN, "crop readout vs page")


if __name__ == "__main__":
    unittest.main()
