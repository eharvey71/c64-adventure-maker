"""Tests for the scene crop band.

The C64 split screen shows only 96 of a Koala scene's 200 rows. These pin
which rows ship, that the choice is per-scene, and that the Scenes-tab
preview marks the same band the exporter writes.
"""
import base64
import json
import struct
import sys
import tempfile
import unittest
import zlib
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

import adventure_editor_v7 as ed  # noqa: E402


def koala_with_row_marks():
    """A Koala image whose every 8-row cell band is a distinct color, so a
    decoded row identifies which source row it came from."""
    data = bytearray(10001)
    for cy in range(25):
        for cx in range(40):
            cell = cy * 40 + cx
            # bitmap bits all 01 -> every pixel takes the screen hi nibble
            for row in range(8):
                data[cell * 8 + row] = 0b01010101
            data[8000 + cell] = ((cy % 15 + 1) << 4)
    data[10000] = 0
    return bytes(data)


def read_png(path):
    """Minimal PNG reader for the 8-bit RGB files the editor writes."""
    raw = Path(path).read_bytes()
    assert raw[:8] == b"\x89PNG\r\n\x1a\n"
    pos, width, height, idat = 8, None, None, b""
    while pos < len(raw):
        (length,) = struct.unpack(">I", raw[pos:pos + 4])
        tag = raw[pos + 4:pos + 8]
        body = raw[pos + 8:pos + 8 + length]
        if tag == b"IHDR":
            width, height = struct.unpack(">II", body[:8])
        elif tag == b"IDAT":
            idat += body
        pos += 12 + length
    data = zlib.decompress(idat)
    stride = width * 3
    rows = []
    for y in range(height):
        start = y * (stride + 1)
        assert data[start] == 0, "only filter type 0 is written"
        rows.append(data[start + 1:start + 1 + stride])
    return width, height, rows


class TestNormalizeCropOffset(unittest.TestCase):
    def test_snaps_to_cell_alignment(self):
        # Off-cell offsets break the compiler's PNG->bitmap round trip.
        for v in range(0, ed.CROP_MAX + 1):
            self.assertEqual(ed.normalize_crop_offset(v) % ed.CROP_STEP, 0)

    def test_clamps_to_legal_range(self):
        self.assertEqual(ed.normalize_crop_offset(-100), 0)
        self.assertEqual(ed.normalize_crop_offset(10**6), ed.CROP_MAX)

    def test_band_always_fits_inside_the_image(self):
        for v in (-5, 0, 51, 104, 999):
            self.assertLessEqual(
                ed.normalize_crop_offset(v) + ed.CROP_ROWS, 200)

    def test_tolerates_junk(self):
        for v in (None, "", "abc", [], {}):
            self.assertEqual(ed.normalize_crop_offset(v), 0)

    def test_accepts_floats_from_the_slider(self):
        self.assertEqual(ed.normalize_crop_offset(51.7), 48)

    def test_constants_are_consistent(self):
        self.assertEqual(ed.CROP_MAX, 200 - ed.CROP_ROWS)
        self.assertEqual(ed.CROP_CENTERED % ed.CROP_STEP, 0)
        self.assertLessEqual(ed.CROP_CENTERED, ed.CROP_MAX)


class TestExportedBand(unittest.TestCase):
    """The written PNG must contain exactly the rows the offset selects."""

    @classmethod
    def setUpClass(cls):
        cls.koala = base64.b64encode(koala_with_row_marks()).decode("ascii")
        cls.native, _, _ = ed.decode_koala_to_rgb(koala_with_row_marks())

    def band_for(self, offset):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "room01_C64.png"
            ed.koala_to_room_png(self.koala, out, offset)
            return read_png(out)

    def test_output_geometry_is_320x96(self):
        w, h, rows = self.band_for(0)
        self.assertEqual((w, h), (320, ed.CROP_ROWS))
        self.assertEqual(len(rows), ed.CROP_ROWS)

    def test_rows_match_the_selected_source_rows(self):
        for offset in (0, 48, 104):
            _, _, rows = self.band_for(offset)
            for i, row in enumerate(rows):
                src_y = offset + i
                want = self.native[src_y * 160 * 3:src_y * 160 * 3 + 3]
                self.assertEqual(
                    bytes(row[:3]), bytes(want),
                    f"offset {offset}, output row {i} is not source row {src_y}")

    def test_different_offsets_select_different_art(self):
        _, _, top = self.band_for(0)
        _, _, bottom = self.band_for(104)
        self.assertNotEqual(top[0], bottom[0])

    def test_offset_is_snapped_before_use(self):
        # 52 is not cell-aligned; it must behave exactly like 48.
        _, _, snapped = self.band_for(52)
        _, _, aligned = self.band_for(48)
        self.assertEqual(snapped, aligned)

    def test_pixels_are_doubled_horizontally(self):
        _, _, rows = self.band_for(0)
        row = rows[0]
        for x in range(0, 320, 2):
            self.assertEqual(row[x * 3:x * 3 + 3], row[(x + 1) * 3:(x + 1) * 3 + 3])


class TestPerSceneCrop(unittest.TestCase):
    """Each scene carries its own band; the converter must honour it."""

    def game_with(self, scene_crop):
        scene = {"name": "art",
                 "koala_b64": base64.b64encode(
                     koala_with_row_marks()).decode("ascii")}
        if scene_crop is not None:
            scene["crop_offset"] = scene_crop
        return {
            "settings": {"startroom": 1},
            "rooms": {"1": {"name": "R", "description": "D",
                            "exits": [0, 0, 0, 0], "scene_id": "ART"}},
            "objects": {}, "vocabulary": {}, "messages": {}, "responses": [],
            "scenes": {"ART": scene},
        }

    def render(self, scene_crop, fallback=0):
        conv = ed.Converter(self.game_with(scene_crop), crop_offset=fallback)
        with tempfile.TemporaryDirectory() as d:
            conv.write_room_images(Path(d))
            return read_png(Path(d) / "room01_C64.png")[2]

    def test_scene_crop_is_used(self):
        self.assertNotEqual(self.render(0), self.render(104))

    def test_scene_crop_overrides_the_converter_fallback(self):
        self.assertEqual(self.render(104, fallback=0),
                         self.render(104, fallback=48))

    def test_missing_scene_crop_uses_the_fallback(self):
        self.assertEqual(self.render(None, fallback=104), self.render(104))

    def test_legacy_scenes_keep_the_historical_top_band(self):
        # Scenes saved before the crop control existed must not be silently
        # re-framed: no crop_offset key still means rows 0-95.
        self.assertEqual(self.render(None, fallback=ed.STORYTLLR_CROP_OFFSET),
                         self.render(0))

    def test_bad_scene_crop_does_not_crash_the_export(self):
        for bad in ("nonsense", None, -40, 9999):
            rows = self.render(bad, fallback=0)
            self.assertEqual(len(rows), ed.CROP_ROWS)

    def test_two_scenes_can_use_different_bands(self):
        game = self.game_with(0)
        game["scenes"]["ART2"] = dict(game["scenes"]["ART"], crop_offset=104)
        game["rooms"]["2"] = {"name": "R2", "description": "D",
                              "exits": [0, 0, 0, 0], "scene_id": "ART2"}
        conv = ed.Converter(game)
        with tempfile.TemporaryDirectory() as d:
            conv.write_room_images(Path(d))
            a = read_png(Path(d) / "room01_C64.png")[2]
            b = read_png(Path(d) / "room02_C64.png")[2]
        self.assertNotEqual(a, b)


class TestPreviewMarksTheSameBand(unittest.TestCase):
    """The preview must agree with the exporter about what ships."""

    def ppm_rows(self, crop_offset, y_scale=1):
        ppm = ed.koala_to_ppm_bytes(koala_with_row_marks(), x_scale=1,
                                    y_scale=y_scale, crop_offset=crop_offset)
        header, body = ppm.split(b"255\n", 1)
        w, h = (int(n) for n in header.split(b"\n")[1].split())
        return [body[y * w * 3:(y + 1) * w * 3] for y in range(h)]

    def test_preview_keeps_full_height(self):
        self.assertEqual(len(self.ppm_rows(48)), 200)

    def test_rows_inside_the_band_are_undimmed(self):
        plain = ed.koala_to_ppm_bytes(koala_with_row_marks(), x_scale=1)
        plain_body = plain.split(b"255\n", 1)[1]
        marked = self.ppm_rows(48)
        for y in range(49, 48 + ed.CROP_ROWS - 1):   # interior of the band
            self.assertEqual(marked[y], plain_body[y * 160 * 3:(y + 1) * 160 * 3],
                             f"row {y} inside the band was altered")

    def test_rows_outside_the_band_are_dimmed(self):
        plain = ed.koala_to_ppm_bytes(koala_with_row_marks(), x_scale=1)
        plain_body = plain.split(b"255\n", 1)[1]
        marked = self.ppm_rows(48)
        for y in (0, 20, 47, 144, 199):
            before = sum(plain_body[y * 160 * 3:(y + 1) * 160 * 3])
            after = sum(marked[y])
            self.assertLess(after, before, f"row {y} outside the band not dimmed")

    def test_band_edges_are_marked(self):
        marked = self.ppm_rows(48)
        for edge in (48, 48 + ed.CROP_ROWS - 1):
            self.assertEqual(bytes(marked[edge][:3]), bytes(ed.BAND_EDGE_RGB))

    def test_marked_band_tracks_the_offset(self):
        for offset in (0, 48, 104):
            marked = self.ppm_rows(offset)
            self.assertEqual(bytes(marked[offset][:3]), bytes(ed.BAND_EDGE_RGB))

    def test_dimming_survives_vertical_scaling(self):
        rows = self.ppm_rows(48, y_scale=2)
        self.assertEqual(len(rows), 400)
        self.assertEqual(bytes(rows[48 * 2][:3]), bytes(ed.BAND_EDGE_RGB))
        self.assertEqual(bytes(rows[48 * 2 + 1][:3]), bytes(ed.BAND_EDGE_RGB))

    def test_without_crop_offset_nothing_is_altered(self):
        plain = ed.koala_to_ppm_bytes(koala_with_row_marks(), x_scale=1)
        same = ed.koala_to_ppm_bytes(koala_with_row_marks(), x_scale=1,
                                     crop_offset=None)
        self.assertEqual(plain, same)


if __name__ == "__main__":
    unittest.main()
