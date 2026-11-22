"""Tests for c64build: the pure-Python petcat and c1541 replacements.

Three layers:

* Fixed vectors captured from VICE 3.7.1. They run everywhere and pin
  petcat's rules, including the odd ones (abbreviations, the DATA quirk).
* Disk structure, read back with a small reader written separately from
  the writer, so the two can't share a mistake.
* Live comparison with the real petcat and c1541 over seeded random input.
  These skip where VICE isn't installed; CI installs it on Linux.
"""
import os
import random
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

import c64build as cb  # noqa: E402

RUNTIME = REPO / "legacy" / "advplay-c64-current.bas"


def body(source):
    """Tokenised bytes of a one-line program, without link or line number."""
    prg = cb.tokenize_basic(source)
    return prg[6:-3]


class TestTokenizerVectors(unittest.TestCase):
    """Each expectation is what petcat -w2 (VICE 3.7.1) produced."""

    def check(self, source, expected_hex):
        self.assertEqual(body(source).hex(" "), expected_hex, source)

    def test_keywords_and_strings(self):
        self.check('10 print"hi"', "99 22 48 49 22")

    def test_spaces_after_the_line_number_are_dropped(self):
        self.check('10   print "hi"', "99 20 22 48 49 22")

    def test_a_tab_after_the_line_number_is_dropped_too(self):
        self.check('10\t"x', "22 58")

    def test_uppercase_is_never_a_keyword(self):
        self.check('10 PRINT "Hi"', "d0 d2 c9 ce d4 20 22 c8 49 22")

    def test_question_mark_is_not_print(self):
        self.check("10 ? 1", "3f 20 31")

    def test_rem_stops_tokenising(self):
        self.check('10 rem print "x"', "8f 20 50 52 49 4e 54 20 22 58 22")

    def test_data_stops_tokenising_until_a_colon(self):
        self.check("10 data print,goto:print",
                   "83 20 50 52 49 4e 54 2c 47 4f 54 4f 3a 99")

    def test_data_ends_at_a_colon_even_inside_quotes(self):
        # petcat's quirk; the C64's own editor would keep DATA going
        self.check('10 data "a:b",print:goto',
                   "83 20 22 41 3a 42 22 2c 99 3a 89")

    def test_keywords_hide_inside_variable_names(self):
        self.check("10 fort=atob", "81 54 b2 41 a4 42")
        self.check("10 score=total+1", "53 43 b0 45 b2 a4 54 41 4c aa 31")

    def test_longest_keyword_wins(self):
        self.check("10 print#1,a", "98 31 2c 41")
        self.check("10 go to 10", "cb 20 a4 20 31 30")

    def test_abbreviations(self):
        self.check("10 sPRINT", "a6 d2 c9 ce d4")      # sP = SPC(
        self.check("10 priGoto", "50 c9 4f a4")        # riG = RIGHT$

    def test_an_abbreviation_tie_goes_to_the_later_keyword(self):
        # tA abbreviates both TAB( and TAN; petcat takes TAN
        self.check("10 dimtA", "86 c0")

    def test_pi_is_not_spelled_but_tilde_is_pi(self):
        self.check("10 x=pi", "58 b2 50 49")
        self.check("10 x=~", "58 b2 ff")

    def test_operators(self):
        self.check("10 a=b>=c", "41 b2 42 b1 b2 43")

    def test_character_map(self):
        self.check('10 a$="@`[\\]^_|}"',
                   "41 24 b2 22 40 40 5b 5c 5d 5e 5f 5c 5d 22")

    def test_control_codes_inside_quotes(self):
        self.check('10 a$="{clr}{CLR}{$41}{147}{lower case}"',
                   "41 24 b2 22 93 93 41 93 0e 22")

    def test_control_codes_outside_quotes_are_literal(self):
        self.check("10 a{home}", "41 5b 48 4f 4d 45 5d")

    def test_an_unknown_control_code_is_refused(self):
        for code in ("{bogus}", "{Clr}", "{rvs on}", "{3 down}"):
            with self.assertRaises(cb.BasicError, msg=code):
                cb.tokenize_basic(f'10 a$="{code}"')

    def test_line_structure(self):
        self.assertEqual(cb.tokenize_basic("10 print 1\r\n20 print 2\r\n").hex(" "),
                         "01 08 09 08 0a 00 99 20 31 00 11 08 14 00 99 20 32 00 00 00")

    def test_lines_keep_file_order(self):
        self.assertEqual(cb.tokenize_basic("20 end\n10 end\n").hex(" "),
                         "01 08 07 08 14 00 80 00 0d 08 0a 00 80 00 00 00")

    def test_a_bare_line_number_is_dropped(self):
        self.assertEqual(cb.tokenize_basic("5\n").hex(" "), "01 08 00 00")

    def test_a_semicolon_line_is_a_comment(self):
        self.assertEqual(cb.tokenize_basic("; note\n10 end\n"),
                         cb.tokenize_basic("10 end\n"))

    def test_line_63999_is_fine(self):
        self.assertEqual(cb.tokenize_basic("63999 end").hex(" "),
                         "01 08 07 08 ff f9 80 00 00 00")

    def test_line_64000_is_refused(self):
        # petcat writes it; a C64 can't list or run it
        with self.assertRaises(cb.BasicError):
            cb.tokenize_basic("64000 end")

    def test_a_line_without_a_number_is_refused(self):
        # petcat silently numbers it two past the previous line
        with self.assertRaises(cb.BasicError):
            cb.tokenize_basic("10 end\nprint 1\n")


# ------------------------------------------------------------ disk reader --
# Deliberately independent of c64build's writer.

TRACK_SECTORS = [21] * 17 + [19] * 7 + [18] * 6 + [17] * 5


def sector(image, t, s):
    o = (sum(TRACK_SECTORS[:t - 1]) + s) * 256
    return image[o:o + 256]


def read_directory(image):
    """[(name, type, first (t, s), blocks, data)] as a C64 would see them."""
    out = []
    t, s = 18, 1
    while t:
        sec = sector(image, t, s)
        for e in range(8):
            ent = sec[e * 32:(e + 1) * 32]
            if ent[2] == 0:
                continue
            name = ent[5:21].rstrip(b"\xa0")
            ft, fs = ent[3], ent[4]
            data, chain = b"", 0
            while ft:
                ds = sector(image, ft, fs)
                chain += 1
                if ds[0]:
                    data += ds[2:]
                else:
                    data += ds[2:ds[1] + 1]
                ft, fs = ds[0], ds[1]
            out.append((name, ent[2], (ent[3], ent[4]),
                        ent[30] | ent[31] << 8, chain, data))
        t, s = sec[0], sec[1]
    return out


class TestDiskLayout(unittest.TestCase):
    def setUp(self):
        self.prg = cb.tokenize_basic(RUNTIME.read_text())
        self.adv = b"ROOM 1\r" * 300
        d = cb.D64("the_haunted_cast", "01")
        d.add_file("advplay", self.prg, "prg")
        d.add_file("game.adv", self.adv, "seq")
        self.image = d.to_bytes()

    def test_the_image_is_a_standard_35_track_disk(self):
        self.assertEqual(len(self.image), 174848)

    def test_header(self):
        bam = sector(self.image, 18, 0)
        self.assertEqual(bam[0:4], bytes([18, 1, 0x41, 0]))
        self.assertEqual(bam[0x90:0xA0], b"THE_HAUNTED_CAST")
        self.assertEqual(bam[0xA2:0xA4], b"01")
        self.assertEqual(bam[0xA5:0xA7], b"2A")

    def test_both_files_read_back_intact(self):
        files = read_directory(self.image)
        self.assertEqual([(f[0], f[1]) for f in files],
                         [(b"ADVPLAY", 0x82), (b"GAME.ADV", 0x81)])
        self.assertEqual(files[0][5], self.prg)
        self.assertEqual(files[1][5], self.adv)

    def test_block_counts_match_the_chains(self):
        for name, _type, _ts, blocks, chain, _data in read_directory(self.image):
            self.assertEqual(blocks, chain, name)

    def test_the_bam_agrees_with_what_is_used(self):
        bam = sector(self.image, 18, 0)
        used = {(18, 0), (18, 1)}
        for _n, _t, (t, s), _b, _c, _d in read_directory(self.image):
            while t:
                used.add((t, s))
                t, s = sector(self.image, t, s)[0:2]
        for track in range(1, 36):
            entry = bam[4 * track:4 * track + 4]
            bits = entry[1] | entry[2] << 8 | entry[3] << 16
            for s in range(TRACK_SECTORS[track - 1]):
                self.assertEqual(bool(bits >> s & 1), (track, s) not in used,
                                 f"track {track} sector {s}")
            self.assertEqual(entry[0], bin(bits).count("1"), f"track {track}")

    def test_files_never_go_on_the_directory_track(self):
        for _n, _t, (t, s), _b, _c, _d in read_directory(self.image):
            while t:
                self.assertNotEqual(t, 18)
                t, s = sector(self.image, t, s)[0:2]

    def test_an_empty_file_still_takes_one_block(self):
        d = cb.D64("x")
        d.add_file("empty", b"", "seq")
        (_n, _t, _ts, blocks, chain, data), = read_directory(d.to_bytes())
        self.assertEqual((blocks, chain, data), (1, 1, b""))

    def test_a_full_disk_is_reported(self):
        d = cb.D64("x")
        with self.assertRaises(cb.DiskError):
            d.add_file("big", bytes(700 * 254), "seq")

    def test_names_are_checked(self):
        d = cb.D64("x")
        for bad in ("", "a" * 17, "a,b", 'a"b'):
            with self.assertRaises(cb.DiskError, msg=bad):
                d.add_file(bad, b"x")


# ------------------------------------------------------- against real VICE --

PETCAT = shutil.which("petcat")
C1541 = shutil.which("c1541")


@unittest.skipUnless(PETCAT, "petcat (VICE) not installed")
class TestMatchesPetcat(unittest.TestCase):
    def petcat(self, source):
        with tempfile.TemporaryDirectory() as d:
            src, out = Path(d, "in.bas"), Path(d, "out.prg")
            src.write_bytes(source.encode())
            subprocess.run([PETCAT, "-w2", "-o", str(out), "--", str(src)],
                           capture_output=True)
            return out.read_bytes() if out.exists() else None

    def test_the_runtime(self):
        text = RUNTIME.read_text()
        self.assertEqual(cb.tokenize_basic(text), self.petcat(text))

    def test_random_programs(self):
        keywords = list(cb._KEYWORDS)
        frags = ["a", "b", "x", "t", "c$", "i%", "10", "3.5", "st", "fo", "pri",
                 "ta", "at", "sc", "ore", "pi", "PRINT", "Goto", "A", "Z"]
        punct = list(" ,;:()+-*/^<>=.$%#&'!?@`[]\\|_~}") + ['"', '"', ":", "\t"]
        ctrl = ["{clr}", "{CLR}", "{$41}", "{147}", "{f1}", "{lower case}"]
        rng = random.Random(64)
        for _ in range(150):
            lines = []
            for _ in range(rng.randint(1, 8)):
                parts = []
                for _ in range(rng.randint(0, 20)):
                    r = rng.random()
                    parts.append(rng.choice(keywords if r < .3 else frags if r < .55
                                            else punct if r < .95 else ctrl))
                lines.append(f"{rng.randint(0, 63999)} {''.join(parts)}")
            source = "\n".join(lines) + "\n"
            self.assertEqual(cb.tokenize_basic(source), self.petcat(source),
                             source)


@unittest.skipUnless(C1541, "c1541 (VICE) not installed")
class TestMatchesC1541(unittest.TestCase):
    def c1541(self, label, disk_id, files):
        """One c1541 process per step, as the editor used to run it."""
        with tempfile.TemporaryDirectory() as d:
            img = os.path.join(d, "t.d64")
            subprocess.run([C1541, "-format", f"{label},{disk_id}", "d64", img],
                           capture_output=True)
            for i, (name, data, kind) in enumerate(files):
                src = os.path.join(d, f"f{i}")
                Path(src).write_bytes(data)
                subprocess.run([C1541, "-attach", img, "-write", src,
                                f"{name},{kind[0]}"], capture_output=True)
            return Path(img).read_bytes()

    def mine(self, label, disk_id, files):
        d = cb.D64(label, disk_id)
        for name, data, kind in files:
            d.add_file(name, data, kind)
        return d.to_bytes()

    def test_the_text_disk(self):
        files = [("advplay", cb.tokenize_basic(RUNTIME.read_text()), "prg"),
                 ("game.adv", b"ROOM\r" * 700, "seq")]
        self.assertEqual(self.mine("the_haunted_cast", "01", files),
                         self.c1541("the_haunted_cast", "01", files))

    def test_random_disks(self):
        # Sizes chosen to cross track zones, switch sides and need extra
        # directory sectors, while staying under the disk's capacity.
        rng = random.Random(1541)
        chars = "abcdefghijklmnopqrstuvwxyz0123456789._"
        for _ in range(12):
            nfiles = rng.choice([1, 3, 12, 20])
            budget = rng.choice([60, 300, 600]) * 254 // nfiles
            files = []
            for k in range(nfiles):
                name = f"{k}" + "".join(rng.choice(chars)
                                        for _ in range(rng.randint(0, 14)))
                size = rng.choice([0, 1, 254, 255, rng.randint(1, budget)])
                files.append((name, bytes(rng.randrange(256) for _ in range(size)),
                              rng.choice(["prg", "seq"])))
            label = "".join(rng.choice(chars) for _ in range(rng.randint(1, 16)))
            self.assertEqual(self.mine(label, "01", files),
                             self.c1541(label, "01", files),
                             f"{label}: {[(f[0], len(f[1])) for f in files]}")


if __name__ == "__main__":
    unittest.main()
