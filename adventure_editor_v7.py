#!/usr/bin/env python3
"""
C64 Adventure Maker - Editor with Game Engine, Player, and one-click C64 build (v7)

Game engine faithfully mirrors advplay-c64-v3.bas logic.

Export paths:
  * File > Export & Build C64 Disk  - ONE CLICK: converts the game, compiles
    it, and builds a ready-to-play .d64 disk image (optionally launching the
    VICE emulator). Rooms with Koala scenes attached get their artwork on
    the C64 split screen; rooms without get generated placeholder images.
    Needs: the patched script_compiler, and VICE (c1541 + x64sc). The kit's
    engine/ folder (storytllr64.prg, stdlib.hjt, font.png) supplies the rest.
  * File > Export StoryTllr Project - writes just the project folder for
    manual building (same content, no compile/disk step).
  * File > Export .adv              - text-only game for advplay-c64-v3.bas

The Scenes tab (from v4/v5) remains the way to import Koala art and attach it
to rooms; the art now flows out through the StoryTllr export. The v4/v5
experiment of pushing scenes through the BASIC runtime (.kla sidecars,
scene sections in .adv, in-editor scene rendering) is removed - it never
worked well. The in-editor Player tab is text-only (and fast) again,
matching what the BASIC runtime actually does.

The v5 engine-fidelity fixes are all retained (ID-prefix object matching,
no generic response fallback, REMOVE "gone" state, WINXXX play-again).

NOTE: the StoryTllr compiler needs the patches in fix_storytllr_compiler.sh
(shortdict split byte, bufferedimgs, all-same shortcut) or graphics will be
missing or corrupt.
"""

try:
    import tkinter as tk
    from tkinter import ttk, filedialog, messagebox
except ImportError:  # pragma: no cover - headless environments
    # The editor UI needs Tkinter, but Converter/GameEngine do not. Keeping
    # the import optional lets the conversion and game-logic layers be
    # imported (and tested) on machines with no GUI toolkit installed.
    tk = ttk = filedialog = messagebox = None
import base64
import glob
import json
import copy
import os
import shutil
import struct
import zlib
from pathlib import Path


# Directories searched for the VICE tools (c1541, x64sc) when they are not
# already on PATH. `~` expands to the home directory; glob wildcards are
# allowed, since VICE ships under version-stamped folder names.
VICE_DIRS = [
    # macOS — Homebrew, MacPorts, and the official .app-style distributions
    "/opt/homebrew/bin", "/usr/local/bin", "/opt/local/bin",
    "/Applications/vice-*/bin",
    "/Applications/VICE/*.app/Contents/Resources/bin",
    "~/Applications/vice-*/bin",
    # Linux — distro packages land on PATH, but snap/flatpak/manual do not
    "/usr/bin", "/usr/local/bin", "/usr/games",
    "/snap/bin", "/var/lib/flatpak/exports/bin",
    "~/.local/bin", "~/vice/bin", "/opt/vice/bin",
    # Windows
    "C:/Program Files/VICE*", "C:/Program Files/VICE*/bin",
    "C:/Program Files (x86)/VICE*", "C:/Program Files (x86)/VICE*/bin",
    "C:/vice*", "C:/vice*/bin",
]


# ---------------------------------------------------------------------------
# C64 KOALA MULTICOLOR BITMAP DECODER
# ---------------------------------------------------------------------------
# Standard "Pepto" C64 palette — 16 RGB triplets.
# Koala format is the de-facto authoring format for C64 multicolor bitmaps.
# 160×200 visual pixels, 4 colors per 4×8 cell (3 free + 1 shared background).
#
# File layout (10001 bytes, or 10003 with 2-byte load address prefix):
#   [0000..7999]  bitmap data           (8000 bytes, 8 bytes per cell, 25×40 cells)
#   [8000..8999]  screen RAM            (1000 bytes; hi nibble=color01, lo nibble=color10)
#   [9000..9999]  color RAM             (1000 bytes; color11)
#   [10000]       background color      (1 byte; color00, shared globally)

C64_PALETTE = [
    (0x00, 0x00, 0x00),  #  0 black
    (0xff, 0xff, 0xff),  #  1 white
    (0x68, 0x37, 0x2b),  #  2 red
    (0x70, 0xa4, 0xb2),  #  3 cyan
    (0x6f, 0x3d, 0x86),  #  4 purple
    (0x58, 0x8d, 0x43),  #  5 green
    (0x35, 0x28, 0x79),  #  6 blue
    (0xb8, 0xc7, 0x6f),  #  7 yellow
    (0x6f, 0x4f, 0x25),  #  8 orange
    (0x43, 0x39, 0x00),  #  9 brown
    (0x9a, 0x67, 0x59),  # 10 light red
    (0x44, 0x44, 0x44),  # 11 dark grey
    (0x6c, 0x6c, 0x6c),  # 12 medium grey
    (0x9a, 0xd2, 0x84),  # 13 light green
    (0x6c, 0x5e, 0xb5),  # 14 light blue
    (0x95, 0x95, 0x95),  # 15 light grey
]


def strip_koala_load_address(data):
    """
    Koala files commonly ship with a 2-byte load address ($6000 → 00 60) at the
    front. If we see 10003 bytes, assume load address is present and drop it.
    Returns exactly 10001 payload bytes, or raises ValueError.
    """
    if isinstance(data, str):
        data = data.encode("latin1")

    if len(data) == 10003:
        return bytes(data[2:])
    if len(data) == 10001:
        return bytes(data)
    # Some tools omit the trailing background byte or add junk; be tolerant.
    if len(data) >= 10002:
        return bytes(data[-10001:])
    raise ValueError(
        f"Not a valid Koala image: expected 10001 or 10003 bytes, got {len(data)}"
    )


def decode_koala_to_rgb(raw_bytes):
    """
    Decode a Koala payload into raw RGB bytes at native 160×200 resolution.
    Returns (rgb_bytes, width=160, height=200).
    """
    data   = strip_koala_load_address(raw_bytes)
    bitmap = data[0:8000]
    scr    = data[8000:9000]
    col    = data[9000:10000]
    bg     = data[10000] & 0x0f

    px = bytearray(160 * 200 * 3)
    for cy in range(25):
        for cx in range(40):
            cell = cy * 40 + cx
            c01  = (scr[cell] >> 4) & 0x0f    # bit-pair 01
            c10  = scr[cell] & 0x0f           # bit-pair 10
            c11  = col[cell] & 0x0f           # bit-pair 11
            for row in range(8):
                byte = bitmap[cell * 8 + row]
                y    = cy * 8 + row
                # Each byte encodes 4 pixels, 2 bits each, high bits leftmost.
                for pp in range(4):
                    bits = (byte >> (6 - pp * 2)) & 0x03
                    if   bits == 0: ci = bg
                    elif bits == 1: ci = c01
                    elif bits == 2: ci = c10
                    else:           ci = c11
                    r, g, b = C64_PALETTE[ci & 0x0f]
                    off = (y * 160 + (cx * 4 + pp)) * 3
                    px[off]     = r
                    px[off + 1] = g
                    px[off + 2] = b
    return bytes(px), 160, 200


# The C64 split screen shows a 96-row band of the 200-row Koala scene. The
# band's top row (the "crop offset") must be cell-aligned — a multiple of 8 —
# so the compiler's PNG->bitmap conversion round-trips losslessly.
CROP_ROWS = 96                       # rows that reach the C64
CROP_STEP = 8                        # cell alignment
CROP_MAX  = 200 - CROP_ROWS          # 104: lowest legal band start
CROP_CENTERED = ((CROP_MAX // 2) // CROP_STEP) * CROP_STEP   # 48

# Preview styling for the rows that will not ship.
BAND_DIM_NUM, BAND_DIM_DEN = 7, 25   # ~28% brightness outside the band
BAND_EDGE_RGB = (0xff, 0x00, 0x80)   # marker rule at the band edges


def normalize_crop_offset(value):
    """Snap a crop offset to a legal, cell-aligned band start in 0..104."""
    try:
        v = int(value)
    except (TypeError, ValueError):
        return 0
    v = max(0, min(CROP_MAX, v))
    return (v // CROP_STEP) * CROP_STEP


def koala_to_ppm_bytes(raw_bytes, x_scale=2, y_scale=1, crop_offset=None):
    """
    Convert Koala to PPM P6 bytes suitable for tk.PhotoImage(data=...).
    Default scales (x=2, y=1) correct C64 multicolor pixel aspect (2:1 wide).
    Bigger scales just multiply. Nearest-neighbour — crisp pixels, no blur.

    Uses `bytes * n` slice replication rather than per-byte writes; the C
    implementation is 10–20× faster than a Python loop and keeps large
    scales (4×2 = 640×400) rendering in well under 100ms.
    """
    rgb, w, h = decode_koala_to_rgb(raw_bytes)
    new_w = w * x_scale
    new_h = h * y_scale
    row_size = new_w * 3
    out = bytearray(row_size * new_h)

    for sy in range(h):
        src_off = sy * w * 3
        if x_scale == 1:
            row = bytes(rgb[src_off : src_off + w * 3])
        else:
            row = bytearray(row_size)
            for sx in range(w):
                pix = rgb[src_off + sx * 3 : src_off + sx * 3 + 3]  # 3 bytes
                base = sx * x_scale * 3
                # Replicate the 3-byte pixel x_scale times in one operation.
                # `pix * n` returns bytes of length 3*n; slice-assign it in.
                row[base : base + x_scale * 3] = pix * x_scale
            row = bytes(row)
        # Repeat the expanded row y_scale times in one slice-assign.
        base_y = sy * y_scale * row_size
        out[base_y : base_y + row_size * y_scale] = row * y_scale

    if crop_offset is not None:
        _dim_rows_outside_band(out, row_size, h, y_scale,
                               normalize_crop_offset(crop_offset))

    header = f"P6\n{new_w} {new_h}\n255\n".encode("ascii")
    return header + bytes(out)


def _dim_rows_outside_band(out, row_size, src_h, y_scale, crop_offset):
    """
    Darken every scaled row whose source row falls outside the 96-row band
    starting at `crop_offset`, and draw a marker line at each band edge.
    Mutates `out` in place.
    """
    for sy in range(src_h):
        inside = crop_offset <= sy < crop_offset + CROP_ROWS
        edge = sy in (crop_offset, crop_offset + CROP_ROWS - 1)
        if inside and not edge:
            continue
        for rep in range(y_scale):
            base = (sy * y_scale + rep) * row_size
            row = out[base:base + row_size]
            if edge:
                # A bright rule so the band's top and bottom are unmistakable.
                out[base:base + row_size] = bytes(BAND_EDGE_RGB) * (row_size // 3)
            else:
                out[base:base + row_size] = bytes(
                    (v * BAND_DIM_NUM) // BAND_DIM_DEN for v in row)


def make_scene_photo(raw_bytes, x_scale=2, y_scale=1, crop_offset=None):
    """
    Build a tk.PhotoImage from Koala bytes. Caller must keep a reference
    or Tk will garbage-collect the image and it'll disappear from the UI.

    When `crop_offset` is given, rows outside the 96-row band that actually
    reaches the C64 are dimmed and the band is marked, so the preview shows
    what ships rather than the whole 200-row source.
    """
    ppm = koala_to_ppm_bytes(raw_bytes, x_scale=x_scale, y_scale=y_scale,
                             crop_offset=crop_offset)
    return tk.PhotoImage(data=ppm, format="ppm")


# ---------------------------------------------------------------------------
# GAME ENGINE  (mirrors BASIC runtime logic exactly)
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# STORYTLLR EXPORT — converter core
# ---------------------------------------------------------------------------
# Converts the in-memory game into a StoryTllrC64 project. Validated
# end-to-end against the engine's compiler and the C64 player's own
# decoder (see fix_storytllr_compiler.sh for the required compiler patches).
# Key compiler constraints encoded here: variable names in if: expressions
# must be pure letters; synthesized objects must be declared globally;
# images must be named *_C64.png to skip the dither/sharpen preprocessing;
# every room needs an image; img/ must exist before compiling.
# ---------------------------------------------------------------------------

STORYTLLR_CROP_OFFSET = 0   # 96-row band offset into 200-row Koala scenes


def write_png(path, width, height, rgb_rows):
    """rgb_rows: list of `height` bytes objects, each width*3 long."""
    def chunk(tag, data):
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xffffffff))

    raw = b"".join(b"\x00" + row for row in rgb_rows)
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    png = (b"\x89PNG\r\n\x1a\n"
           + chunk(b"IHDR", ihdr)
           + chunk(b"IDAT", zlib.compress(raw, 9))
           + chunk(b"IEND", b""))
    Path(path).write_bytes(png)



def koala_to_room_png(koala_b64, out_path, crop_offset=0):
    """
    Take a 96-row band from a 160x200 Koala scene, double horizontally,
    and write a 320x96 PNG for StoryTllr. crop_offset must be a multiple
    of 8 (cell-aligned) in 0..104 so the compiler's PNG->bitmap conversion
    round-trips losslessly.
    """
    crop_offset = normalize_crop_offset(crop_offset)
    rgb, w, h = decode_koala_to_rgb(base64.b64decode(koala_b64))
    rgb_rows = []
    for y in range(crop_offset, crop_offset + CROP_ROWS):
        row = bytearray()
        src = y * w * 3
        for x in range(w):
            px = rgb[src + x * 3 : src + x * 3 + 3]
            row += px + px                      # 2x horizontal (multicolor aspect)
        rgb_rows.append(bytes(row))
    write_png(out_path, 320, 96, rgb_rows)


# (bg, band) color pairs cycled by room number — distinct, visible C64 pairings.
PLACEHOLDER_THEMES = [
    (6, 14),   # blue / light blue
    (9, 8),    # brown / orange
    (11, 15),  # dark grey / light grey
    (4, 10),   # purple / light red
    (5, 13),   # green / light green
    (2, 10),   # red / light red
    (12, 3),   # medium grey / cyan
    (6, 4),    # blue / purple
]


def placeholder_room_png(room_num, out_path):
    """
    Simple two-tone placeholder: sky/backdrop above a ground band, plus a
    horizon line, all aligned to 8px PNG cells (4px native) so any 4x8
    native cell holds at most 2 colors.
    """
    bg_i, band_i = PLACEHOLDER_THEMES[(room_num - 1) % len(PLACEHOLDER_THEMES)]
    bg, band = C64_PALETTE[bg_i], C64_PALETTE[band_i]
    horizon = 64                       # cell-aligned split (row 64 of 96)
    rgb_rows = []
    for y in range(96):
        color = bg if y < horizon else band
        rgb_rows.append(bytes(color) * 320)
    write_png(out_path, 320, 96, rgb_rows)


# ---------------------------------------------------------------------------
# TEXT-ENGINE COMPATIBILITY
# ---------------------------------------------------------------------------
# legacy/advplay-c64-current.bas now understands everything the editor emits:
# any verb reaches the response table, conditions and actions may be comma
# lists, NOT and AT conditions work, and REMOVE and MSG are implemented.
#
# What remains genuinely graphical-only is room artwork, which the text engine
# has no way to display. Everything else runs in both targets.

# The text runtime's fixed array sizes, from the DIM statements in
# legacy/advplay-c64-current.bas. Overflow is silent: the loader stops
# storing past the limit and the game simply lacks the rest.
#
#   40 dim r$(20,4)   30 dim i$(10)    50 dim m$(10,1)
#   60 dim f$(10)        dim o$(30,4)     dim v$(20,2)   dim rs$(20,3)
#
# The graphical target has no equivalent caps; disk space is its real limit.
BASIC_LIMITS = {
    "rooms":      20,
    "objects":    30,
    "vocabulary": 20,
    "responses":  20,
    "messages":   10,
    "flags":      10,
    "carried":    10,
}


def basic_flag_names(game):
    """Every distinct flag the game sets or tests."""
    names = set()
    for resp in game.get("responses", []):
        for term in (resp.get("action") or "").upper().split(","):
            term = term.strip()
            if term.startswith("SET FLAG."):
                names.add(term[len("SET FLAG."):].strip())
        for term in (resp.get("condition") or "").upper().split(","):
            term = term.strip()
            if term.startswith("NOT "):
                term = term[4:].strip()
            if term.startswith("FLAG."):
                names.add(term[len("FLAG."):].strip())
    return {n for n in names if n}


def resolve_noun(word, objects):
    """Mirror Converter.resolve_object so the editor and the build agree."""
    w = (word or "").upper().strip()
    if not w:
        return None
    for oid in objects:
        if oid.upper().startswith(w):
            return oid
    for oid, od in objects.items():
        if (od.get("name") or "").upper().startswith(w):
            return oid
    for oid, od in objects.items():
        if w in (od.get("name") or "").upper().split():
            return oid
    return None


def undefined_nouns(resp, game):
    """Nouns in a response's command that are not in the Objects list.

    The build invents an invisible stand-in for the first of these, taking
    its room from an AT condition. That works, but the author gets no
    description and the thing is never listed in the room. Declaring it as
    a FIXED object is better and is what GATE and BEAST already are.
    """
    objects = game.get("objects", {})
    words = (resp.get("command") or "").upper().split()[1:]
    return [w for w in words
            if w not in FILLER_WORDS and resolve_noun(w, objects) is None]


def undefined_noun_note(word, resp):
    """The advice an author can act on, rather than a statement of fact."""
    at_room = None
    for term in (resp.get("condition") or "").upper().split(","):
        term = term.strip()
        if term.startswith("AT "):
            at_room = term[3:].strip()
            break
    where = f"room {at_room}" if at_room else "no room"
    tail = (f"The build adds an invisible stand-in in {where}."
            if at_room else
            "With no AT condition saying where it is, the build cannot place "
            "it and this response is left out entirely.")
    return (f"'{word}' is not in your Objects list. {tail} "
            f"To give it a description and have it listed in the room, add "
            f"{word} as an object with properties FIXED - the same as GATE "
            f"and BEAST.")


def basic_capacity(game):
    """Counts against the text runtime's limits, keyed as in BASIC_LIMITS.

    Every value is (count, limit). 'carried' counts takeable objects, which
    is the most a player could ever be holding at once; it is advisory
    rather than a hard authoring limit.
    """
    takeable = sum(
        1 for od in game.get("objects", {}).values()
        if "TAKEABLE" in (od.get("properties") or "").upper())
    return {
        "rooms":      (len(game.get("rooms", {})), BASIC_LIMITS["rooms"]),
        "objects":    (len(game.get("objects", {})), BASIC_LIMITS["objects"]),
        "vocabulary": (len(game.get("vocabulary", {})), BASIC_LIMITS["vocabulary"]),
        "responses":  (len(game.get("responses", [])), BASIC_LIMITS["responses"]),
        "messages":   (len(game.get("messages", {})), BASIC_LIMITS["messages"]),
        "flags":      (len(basic_flag_names(game)), BASIC_LIMITS["flags"]),
        "carried":    (takeable, BASIC_LIMITS["carried"]),
    }


def capacity_text(key, count, limit):
    """One line for a tab header, saying plainly what happens on overflow."""
    if key == "carried":
        if count > limit:
            return (f"{count} takeable objects — the text engine can only hold "
                    f"{limit} at once, so a player could not carry them all.")
        return f"{count} takeable objects (text engine holds {limit} at once)."
    noun = {"vocabulary": "vocabulary entries"}.get(key, key)
    if count > limit:
        return (f"{count} {noun} — the text engine stops at {limit}. "
                f"The last {count - limit} would be missing from a .adv build.")
    return f"{count} of {limit} {noun} used in the text engine."


# Dropped from a command before matching, by both engines.
FILLER_WORDS = {"TO", "ON", "WITH", "AT", "THE", "INTO"}

BASIC_CONDITION_PREFIXES = ("HAS ", "FLAG.", "AT ", "NOT ")
BASIC_ACTION_PREFIXES = ("UNLOCK ", "MOVE TO ", "SET FLAG.", "SCORE ",
                         "WIN", "REMOVE ", "MSG ")


def basic_incompatibilities(resp):
    """Reasons a response will not behave in the text engine as written.

    Returns a list of plain sentences, empty when the response works in both
    targets. Each term of a comma list is checked on its own, since the
    runtime now evaluates them individually.
    """
    reasons = []

    cmd = (resp.get("command") or "").strip()
    if not cmd:
        reasons.append("No command, so nothing can match it.")

    for term in (resp.get("condition") or "").strip().upper().split(","):
        term = term.strip()
        if not term:
            continue
        body = term[4:].strip() if term.startswith("NOT ") else term
        if not body.startswith(("HAS ", "FLAG.", "AT ")):
            reasons.append(
                f"The text engine does not understand the condition "
                f"'{term}', so it is skipped and treated as true.")

    for term in (resp.get("action") or "").strip().upper().split(","):
        term = term.strip()
        if not term:
            continue
        if not term.startswith(BASIC_ACTION_PREFIXES):
            reasons.append(
                f"The text engine has no '{term.split()[0]}' action.")

    return reasons


DIR_NAMES = ["NORTH", "SOUTH", "EAST", "WEST"]      # exits[] index order
DIR_VERBS = ["n", "s", "e", "w"]
DIR_SHORT = {"NORTH": "n", "SOUTH": "s", "EAST": "e", "WEST": "w"}

# Verbs stdlib already defines (with synonyms) — don't redeclare.
STDLIB_VERBS = {"x", "take", "drop", "use", "push", "pull", "open", "close",
                "lock", "unlock", "inventory", "score", "quit", "restart",
                "save", "load", "n", "s", "e", "w", "u", "d",
                "ne", "nw", "se", "sw"}

VERB_MAP = {"EXAMINE": "x", "X": "x", "LOOK": "x"}   # editor verb -> stdlib verb


def slugify(title):
    s = "".join(c if c.isalnum() else "_" for c in title.lower()).strip("_")
    while "__" in s:
        s = s.replace("__", "_")
    return s or "game"


def obj_ident(oid):
    """StoryTllr object identifier: lowercase, alnum."""
    return "".join(c for c in oid.lower() if c.isalnum() or c == "_") or "obj"


def flag_var(name):
    """
    Variable name for a flag. The compiler's if: expression tokenizer
    (ifget in main.c) only accepts pure-alphabetic identifiers, so all
    non-letters are stripped: FLAG.BEAST_DEAD -> fbeastdead.
    """
    return "f" + "".join(c for c in name.lower() if c.isalpha())


def room_letters(room_str):
    """Encode a room number as letters (1->a, 2->b, ... 27->aa) for use
    inside alpha-only variable names."""
    n = int(room_str)
    s = ""
    while n > 0:
        n, rem = divmod(n - 1, 26)
        s = chr(ord("a") + rem) + s
    return s or "a"


def unlock_var(room, direction):
    return f"u{room_letters(room)}{DIR_SHORT[direction]}"


class Converter:
    def __init__(self, game, crop_offset=0):
        self.game = game
        self.crop_offset = crop_offset
        self.warnings = []
        self.notes = []

        self.rooms = game.get("rooms", {})
        self.objects = game.get("objects", {})
        self.vocab = game.get("vocabulary", {})
        self.messages = game.get("messages", {})
        self.responses = game.get("responses", [])
        self.scenes = game.get("scenes", {})
        self.settings = game.get("settings", {})

        # ---- derived state ----
        self.synth_objects = {}     # ident -> {"room": rid, "name": word}
        self.obj_syns = {}          # ident -> set of extra synonyms
        self.unlocks = set()        # (room_str, DIRECTION) needing conditional exits
        self.flags = set()          # flag var names used
        self.groups = {}            # (owner_ident, verb) -> [branch, ...]
        self.group_order = []       # insertion order of group keys
        self.extra_verbs = {}       # verb -> [syns] to declare globally

        self._scan_unlocks()
        self._map_responses()

    # ---- object resolution: ID prefix -> name prefix -> word-in-name ----

    def resolve_object(self, word):
        w = word.upper().strip()
        if not w:
            return None
        for oid in self.objects:
            if oid.upper().startswith(w):
                return oid
        for oid, od in self.objects.items():
            if od.get("name", "").upper().startswith(w):
                return oid
        for oid, od in self.objects.items():
            if w in od.get("name", "").upper().split():
                return oid
        return None

    # ---- pre-scan actions for UNLOCK targets ----

    def _scan_unlocks(self):
        for resp in self.responses:
            for part in resp.get("action", "").split(","):
                ac = part.strip().upper()
                if ac.startswith("UNLOCK "):
                    bits = ac[7:].split()
                    if len(bits) >= 4 and bits[2] == "TO" and bits[0] in DIR_SHORT:
                        self.unlocks.add((bits[1], bits[0], bits[3]))

    # ---- condition / action translation ----

    def translate_conditions(self, cond_str):
        """Return list of StoryTllr if-lines (to be nested)."""
        out = []
        for cond in cond_str.split(","):
            c = cond.strip().upper()
            if not c:
                continue
            if c.startswith("NOT FLAG."):
                fv = flag_var(c[9:])
                self.flags.add(fv)
                out.append(f"if:{fv}=0")
            elif c.startswith("FLAG."):
                fv = flag_var(c[5:])
                self.flags.add(fv)
                out.append(f"if:{fv}=1")
            elif c.startswith("HAS "):
                oid = self.resolve_object(c[4:])
                if oid:
                    out.append(f"ifobjin:{obj_ident(oid)},$inventory")
                else:
                    self.warnings.append(
                        f"A response requires the player to have "
                        f"'{c[4:]}', but no object with that name exists "
                        f"— that requirement will be skipped.")
            elif c.startswith("AT "):
                out.append(f"ifisroom:room{c[3:].strip()}")
            else:
                self.warnings.append(
                    f"A response has a condition I don't recognize "
                    f"('{c}') — it will be skipped.")
        return out

    def translate_actions(self, action_str):
        """Return list of StoryTllr statement lines (flat)."""
        out = []
        for part in action_str.split(","):
            ac = part.strip().upper()
            if not ac:
                continue
            if ac.startswith("UNLOCK "):
                bits = ac[7:].split()
                if len(bits) >= 4 and bits[2] == "TO" and bits[0] in DIR_SHORT:
                    out.append(f"setvar:{unlock_var(bits[1], bits[0])},1")
                else:
                    self.warnings.append(
                        f"An UNLOCK action isn't written correctly "
                        f"('{ac}') — it will be skipped. The format is "
                        f"UNLOCK <DIRECTION> <FROM ROOM> TO <TO ROOM>.")
            elif ac.startswith("SET FLAG."):
                fv = flag_var(ac[9:])
                self.flags.add(fv)
                out.append(f"setvar:{fv},1")
            elif ac.startswith("REMOVE "):
                oid = self.resolve_object(ac[7:])
                if oid:
                    out.append(f"unsetobj:{obj_ident(oid)},visible")
                else:
                    self.warnings.append(
                        f"A REMOVE action names '{ac[7:]}', but no object "
                        f"with that name exists — it will be skipped.")
            elif ac.startswith("MOVE TO "):
                out.append(f"goto:room{ac[8:].strip()}")
            elif ac.startswith("SCORE "):
                out.append(f"addvar:score,{ac[6:].strip()}")
                self.notes.append(
                    "Score always adds up. 'Max Score' appears in the text "
                    "build's final score; the graphical build ignores it.")
            elif ac.startswith("MSG "):
                key = ac[4:].strip()
                text = self.messages.get(key, "")
                if text:
                    out.append(f"msg:{text}")
                else:
                    self.warnings.append(
                        f"A response uses message '{key}', but there's no "
                        f"message with that name in the Messages tab — it "
                        f"will be skipped.")
            elif ac == "WINXXX":
                out.append("__WINXXX__")
            else:
                self.warnings.append(
                    f"A response has an action I don't recognize "
                    f"('{ac}') — it will be skipped.")
        return out

    # ---- response mapping: group into (object, verb) verb blocks ----

    def _map_responses(self):
        for resp in self.responses:
            cmd = resp.get("command", "").strip().upper()
            if not cmd:
                continue
            words = cmd.split()
            verb_word = words[0]
            verb = VERB_MAP.get(verb_word, verb_word.lower())

            nouns = words[1:]
            owner = None
            guards = []                      # extra presence guards
            unresolved_first = None
            for i, nw in enumerate(nouns):
                oid = self.resolve_object(nw)
                if oid:
                    ident = obj_ident(oid)
                    # remember typed word as a synonym if it isn't the ident
                    if nw.lower() != ident and not self.objects[oid]["name"].upper().startswith(nw):
                        self.obj_syns.setdefault(ident, set()).add(nw.lower())
                    if owner is None:
                        owner = ident
                    else:
                        guards.append(f"ifobjin:{ident},$here")
                elif self.synth_objects.get(nw.lower()):
                    if owner is None:
                        owner = nw.lower()
                    else:
                        guards.append(f"ifobjin:{nw.lower()},$here")
                elif unresolved_first is None and owner is None:
                    unresolved_first = nw

            if owner is None and unresolved_first:
                # Synthesize a sceneryobj in the room named by an AT condition
                at_room = None
                for c in resp.get("condition", "").upper().split(","):
                    c = c.strip()
                    if c.startswith("AT "):
                        at_room = c[3:].strip()
                        break
                ident = unresolved_first.lower()
                if at_room:
                    self.synth_objects[ident] = {"room": at_room, "name": unresolved_first}
                    owner = ident
                    self.notes.append(
                        f"'{unresolved_first}' in '{cmd}' is not in your "
                        f"Objects list. An invisible stand-in will be added "
                        f"to room {at_room} so the command works. To give it "
                        f"a description and have it listed in the room, add "
                        f"{unresolved_first} as an object with properties "
                        f"FIXED — the same as GATE and BEAST.")
                else:
                    self.warnings.append(
                        f"The command '{cmd}' mentions "
                        f"'{unresolved_first}', which isn't a defined "
                        f"object, and the response has no AT <room> "
                        f"condition telling me where it belongs — this "
                        f"response will be left out. Add an AT condition "
                        f"or define the object.")
                    continue

            if owner is None:
                self.warnings.append(
                    f"The command '{cmd}' doesn't mention any object I "
                    f"can attach it to — this response will be left out.")
                continue

            if verb not in STDLIB_VERBS and verb not in self.extra_verbs:
                syns = [verb]
                for base, alts in self.vocab.items():
                    if base.upper() == verb_word:
                        syns += [a.lower() for a in alts]
                self.extra_verbs[verb] = syns

            key = (owner, verb)
            if key not in self.groups:
                self.groups[key] = []
                self.group_order.append(key)
            self.groups[key].append({
                "conditions": guards + self.translate_conditions(resp.get("condition", "")),
                "message": resp.get("message", "").strip(),
                "actions": self.translate_actions(resp.get("action", "")),
            })

    # ---- emission ----

    def emit_win_block(self, ind):
        t = "\t" * ind
        win_msg = (self.settings.get("winmessage")
                   or "CONGRATULATIONS! YOU HAVE WON!")
        return [
            f"{t}msg:{win_msg}",
            f"{t}msg:PLAY AGAIN? (Y/N)",
            f"{t}getkey",
            f"{t}ifkey:Y",
            f"{t}\tstart",
            f"{t}else",
            f"{t}\tquit",
        ]

    def emit_branch_body(self, branch, ind):
        t = "\t" * ind
        lines = []
        if branch["message"]:
            lines.append(f"{t}msg:{branch['message']}")
        for a in branch["actions"]:
            if a == "__WINXXX__":
                lines += self.emit_win_block(ind)
            else:
                lines.append(f"{t}{a}")
        return lines

    def emit_verb_block(self, owner, verb, branches, base_ind):
        """
        Emit one verb block. Multiple branches keep first-match-wins order
        via a scratch var (tmp) exactly like the BASIC response scan.
        Fallback (nothing matched): x -> object description, use -> nothing
        happens, others -> silent (stdlib default kicks in for unknown cases).
        """
        t = "\t" * base_ind
        lines = [f"{t}verb:{verb}"]
        ind = base_ind + 1

        single = (len(branches) == 1 and not branches[0]["conditions"])
        if single:
            lines += self.emit_branch_body(branches[0], ind)
            return lines

        ti = "\t" * ind
        lines.append(f"{ti}setvar:tmp,0")
        for branch in branches:
            depth = ind
            lines.append("\t" * depth + "if:tmp=0")
            depth += 1
            for cond in branch["conditions"]:
                lines.append("\t" * depth + cond)
                depth += 1
            lines.append("\t" * depth + "setvar:tmp,1")
            lines += self.emit_branch_body(branch, depth)

        # fallback, replicating the BASIC path when no response matched
        lines.append(f"{ti}if:tmp=0")
        if verb == "x":
            lines.append(f"{ti}\tmsg:$objdesc")
        elif verb == "use":
            lines.append(f"{ti}\tmsg:NOTHING HAPPENS.")
        else:
            dont = self.messages.get("DONT_UNDERSTAND", "I DON'T UNDERSTAND THAT.")
            lines.append(f"{ti}\tmsg:{dont}")
        return lines

    def emit(self, font_path="..\\shared\\png\\font.png"):
        s = self.settings
        L = []
        L.append("config")
        L.append(f"\tname:{s.get('title', 'Untitled')}")
        L.append(f"\tversion:{s.get('version', '1.0')}")
        L.append(f"\tauthor:{s.get('author', 'unknown')}")
        L.append("\tengine:StoryTllrC64")
        L.append(f"\tfont:{font_path}")
        L.append("\tsplity:96")
        L.append("\tbinary:yes")
        L.append("\timgfolder:img\\")
        L.append("include:stdlib.hjt")

        # Global verb declarations (with vocabulary synonyms)
        for verb, syns in self.extra_verbs.items():
            L.append(f"verb:{verb}")
            if len(syns) > 1:
                L.append(f"\tsyn:{','.join(dict.fromkeys(syns))}")

        # Synthesized objects — declared globally with startin: because the
        # compiler resolves forward references to global objects but NOT to
        # room-nested ones (ifobjin:wizard,$here fails if wizard is nested).
        for ident, meta in self.synth_objects.items():
            # 'scenery' is visible but not listable: present and usable, but
            # the room never announces it. The text build has no object here
            # at all, so this is what keeps the two targets consistent.
            L.append(f"scenery:{ident}")
            L.append(f"\tname:{meta['name']}")
            L.append(f"\tstartin:room{meta['room']}")
            for (owner, verb) in list(self.group_order):
                if owner == ident:
                    L += self.emit_verb_block(owner, verb, self.groups[(owner, verb)], 1)

        # Global objects
        for oid, od in self.objects.items():
            ident = obj_ident(oid)
            props = od.get("properties", "").upper()
            takeable = "TAKEABLE" in props
            # stdlib's classes: normalobj is visible+takeable+listable,
            # sceneryobj is visible+listable, and scenery is visible only.
            # A HIDDEN object is present and interactable but never listed,
            # which is how a secret stays secret in both targets.
            if takeable:
                cls = "normalobj"
            elif "HIDDEN" in props:
                cls = "scenery"
            else:
                cls = "sceneryobj"
            L.append(f"{cls}:{ident}")
            L.append(f"\tname:{od.get('name', oid)}")
            desc = od.get("description", "").strip()
            if desc:
                L.append(f"\tdesc:{desc}")
            syns = {ident}
            first_name_word = od.get("name", "").lower().split()
            if first_name_word:
                syns.add(first_name_word[-1])       # last word of name (CHALICE)
            syns |= self.obj_syns.get(ident, set())
            if syns - {ident}:
                L.append(f"\tsyn:{','.join(sorted(syns))}")
            sr = od.get("start_room", 0)
            if sr == -1:
                L.append("\tstartin:$inventory")
            elif isinstance(sr, int) and sr > 0:
                L.append(f"\tstartin:room{sr}")
            # object-level verb blocks
            for (owner, verb) in list(self.group_order):
                if owner == ident:
                    L += self.emit_verb_block(owner, verb, self.groups[(owner, verb)], 1)

        # Rooms
        room_ids = sorted(self.rooms, key=lambda k: int(k) if str(k).isdigit() else 999)
        for rid in room_ids:
            room = self.rooms[rid]
            L.append(f"room:room{rid}")
            L.append(f"\tname:{room.get('name', f'ROOM {rid}')}")
            L.append(f"\tdesc:{room.get('description', '')}")
            L.append(f"\timage:png\\room{int(rid):02d}_C64.png")

            # exits: static and unlockable
            exits = room.get("exits", [0, 0, 0, 0])
            for i, dest in enumerate(exits):
                direction = DIR_NAMES[i]
                unlockable = next(((r, d, to) for (r, d, to) in self.unlocks
                                   if r == str(rid) and d == direction), None)
                if unlockable:
                    _, _, to = unlockable
                    uv = unlock_var(str(rid), direction)
                    L.append(f"\tverb:{DIR_VERBS[i]}")
                    L.append(f"\t\tif:{uv}=1")
                    L.append(f"\t\t\tgoto:room{to}")
                    L.append("\t\telse")
                    cant = self.messages.get("CANT_GO", "YOU CAN'T GO THAT WAY.")
                    if int(dest) > 0:
                        L.append(f"\t\t\tgoto:room{dest}")
                        self.warnings.append(
                            f"Room {rid} has both a normal {direction} "
                            f"exit and an UNLOCK for the same direction — "
                            f"the UNLOCK wins; the normal exit is used "
                            f"until unlocked.")
                    else:
                        L.append(f"\t\t\tmsg:{cant}")
                elif int(dest) > 0:
                    L.append(f"\tverb:{DIR_VERBS[i]}")
                    L.append(f"\t\tgoto:room{dest}")

        # $start room: title card, var init, jump to start room
        start_room = s.get("startroom", 1)
        L.append("room:$start")
        L.append(f"\timage:png\\room{int(start_room):02d}_C64.png")
        L.append("\tonfirst")
        L.append("\t\tclear")
        L.append("\t\tmsg:\\c\\y##NAME##")
        L.append("\t\t\t\\c")
        L.append("\t\t\t\\c\\wby ##AUTHOR##")
        L.append("\t\t\t\\c")
        L.append("\t\t\t\\c\\gVersion ##VERSION##")
        L.append("\t\twaitkey")
        L.append("\t\tsetvar:score,0")
        L.append("\t\tsetvar:tmp,0")
        for fv in sorted(self.flags):
            L.append(f"\t\tsetvar:{fv},0")
        for (r, d, _to) in sorted(self.unlocks):
            L.append(f"\t\tsetvar:{unlock_var(r, d)},0")
        L.append(f"\t\tgoto:room{start_room}")

        return "\n".join(L) + "\n"

    # ---- image generation ----

    def write_room_images(self, png_dir):
        """
        Images are named roomNN_C64.png deliberately: the compiler treats any
        PNG *not* named *_C64.png as raw artwork and applies dither/sharpen/
        contrast preprocessing, which corrupts already-palette-exact images
        (stray pixels, lines). The _C64 suffix marks them as final.
        """
        png_dir.mkdir(parents=True, exist_ok=True)
        made = []
        for rid, room in self.rooms.items():
            n = int(rid)
            out = png_dir / f"room{n:02d}_C64.png"
            sid = room.get("scene_id")
            scene = self.scenes.get(sid, {}) if sid else {}
            koala = scene.get("koala_b64", "")
            if koala:
                # Per-scene framing wins; self.crop_offset is the fallback for
                # scenes saved before the crop control existed.
                offset = normalize_crop_offset(
                    scene.get("crop_offset", self.crop_offset))
                try:
                    koala_to_room_png(koala, out, offset)
                    made.append((out.name, f"from scene {sid} (rows "
                                           f"{offset}-{offset + CROP_ROWS - 1})"))
                    continue
                except Exception as e:
                    self.warnings.append(
                        f"The scene '{sid}' on room {rid} couldn't be "
                        f"converted ({e}) — a placeholder image is used "
                        f"instead.")
            placeholder_room_png(n, out)
            made.append((out.name, "placeholder"))
        return made



class GameEngine:
    """
    Key BASIC behaviours reproduced here:
      Object in inventory   → start_room == -1          (BASIC: o$(i,1)="-1")
      Condition HAS X       → prefix-match obj NAME in inventory (line 14140)
      Condition FLAG.X      → check flags list           (line 14240)
      Response matching     → rc$ is a substring of c2$ (line 13480)
      Message lookup        → m$(nm,0)=key, m$(nm,1)=text (section [MESSAGES])
      Action UNLOCK dir R TO D → update room exit        (line 15300)
      Action SET FLAG.X     → add to flags list          (line 15200)
      Action MOVE TO room   → teleport player            (line 15100)
    """

    def __init__(self, game_data):
        self.game        = copy.deepcopy(game_data)
        self.current_room = int(self.game["settings"].get("startroom", 1))
        self.score       = 0
        self.max_score   = int(self.game["settings"].get("maxscore", 100))
        self.flags       = []          # list of active flag strings
        self.game_over   = False
        self.win         = False
        self.debug_log   = []

        # Normalise object start_room to int
        for obj in self.game["objects"].values():
            try:
                obj["start_room"] = int(obj["start_room"])
            except (ValueError, TypeError):
                obj["start_room"] = -1

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def dbg(self, msg):
        self.debug_log.append(msg)
        if len(self.debug_log) > 200:
            self.debug_log.pop(0)

    SYSTEM_DEFAULTS = {
        "CANT_GO":         "YOU CAN'T GO THAT WAY.",
        "DONT_UNDERSTAND": "I DON'T UNDERSTAND THAT.",
        "NOT_HERE":        "I DON'T SEE THAT HERE.",
        "INVENTORY_EMPTY": "YOU AREN'T CARRYING ANYTHING.",
        "ITEM_TAKEN":      "TAKEN.",
        "ITEM_DROPPED":    "DROPPED.",
        "WIN_GAME":        "CONGRATULATIONS! YOU HAVE WON!",
    }

    def get_msg(self, key, default=""):
        """Look up message by key — checks game data first, then system defaults."""
        val = self.game.get("messages", {}).get(key)
        if val:
            return val
        return self.SYSTEM_DEFAULTS.get(key, default)

    def get_room(self, room_id):
        return self.game["rooms"].get(str(room_id))

    def current_room_data(self):
        return self.get_room(self.current_room)

    def inventory_objects(self):
        """Return list of (obj_id, obj_data) for objects in inventory."""
        return [(oid, od) for oid, od in self.game["objects"].items()
                if od["start_room"] == -1]

    def room_objects(self, room_id=None):
        """Return list of (obj_id, obj_data) for objects in a room."""
        if room_id is None:
            room_id = self.current_room
        return [(oid, od) for oid, od in self.game["objects"].items()
                if od["start_room"] == int(room_id)]

    # ------------------------------------------------------------------
    # Condition evaluator (BASIC lines 14000-14260)
    # ------------------------------------------------------------------

    def check_condition(self, condition_str):
        """
        Evaluate a condition string.  Multiple conditions are comma-separated;
        ALL must be true (AND logic).

        Supported:
          HAS <name>    – player carries object whose name starts with <name>
          FLAG.<name>   – flag is set
          AT <room_id>  – player is in room
        """
        if not condition_str or not condition_str.strip():
            return True

        for cond in condition_str.split(","):
            cond = cond.strip().upper()
            if not cond:
                continue

            # NOT inverts a term, matching the runtime's line 14410. Without
            # this the term fell through as unrecognised and was treated as
            # true, so NOT FLAG.X held whether or not the flag was set.
            negate = False
            if cond.startswith("NOT "):
                negate = True
                cond = cond[4:].strip()
            if negate:
                inner = self.check_condition(cond)
                self.dbg(f"  COND NOT {cond} → {not inner}")
                if inner:
                    return False
                continue

            if cond.startswith("HAS "):
                # advplay-c64-v3.bas line ~14100-14156: ID prefix first,
                # then name prefix (see find_object docstring).
                want = cond[4:].strip()
                found = False
                for oid, od in self.inventory_objects():
                    if oid.upper().startswith(want):
                        found = True
                        break
                if not found:
                    for oid, od in self.inventory_objects():
                        if od.get("name", "").upper().startswith(want):
                            found = True
                            break
                self.dbg(f"  COND HAS '{want}' → {found}")
                if not found:
                    return False

            elif cond.startswith("FLAG."):
                # BASIC line 14240: exact flag match
                flag_name = cond[5:].strip()
                found = flag_name in self.flags
                self.dbg(f"  COND FLAG.{flag_name} → {found}")
                if not found:
                    return False

            elif cond.startswith("AT "):
                # Room check
                try:
                    want_room = int(cond[3:].strip())
                    found = (self.current_room == want_room)
                    self.dbg(f"  COND AT {want_room} → {found}")
                    if not found:
                        return False
                except ValueError:
                    return False

        return True

    # ------------------------------------------------------------------
    # Action executor (BASIC lines 15000-15890)
    # ------------------------------------------------------------------

    def execute_action(self, action_str):
        """
        Execute a comma-separated list of actions.
        Returns list of extra display lines.

        Supported actions:
          UNLOCK <dir> <from_room> TO <dest_room>
          SET FLAG.<name>
          MOVE TO <room_id>          — teleport player
          REMOVE <obj_id>            — remove object from world (start_room=-2)
          SCORE <points>
          MSG <key>
          WINXXX
        """
        if not action_str or not action_str.strip():
            return []

        msgs = []

        # Split on commas — each part is one action
        for part in action_str.split(","):
            ac = part.strip().upper()
            if not ac:
                continue
            self.dbg(f"  ACTION: {ac}")

            if ac.startswith("UNLOCK "):
                # "UNLOCK SOUTH 7 TO 8"
                rest  = ac[7:]
                parts = rest.split()
                if len(parts) >= 4 and parts[2] == "TO":
                    direction = parts[0]
                    from_room = str(parts[1])
                    dest_room = int(parts[3])
                    dir_map   = {"NORTH": 0, "SOUTH": 1, "EAST": 2, "WEST": 3}
                    dir_idx   = dir_map.get(direction, -1)
                    if dir_idx >= 0 and from_room in self.game["rooms"]:
                        self.game["rooms"][from_room]["exits"][dir_idx] = dest_room
                        self.dbg(f"  UNLOCKED {direction} from {from_room} → {dest_room}")

            elif ac.startswith("SET FLAG."):
                flag_name = ac[9:].strip()
                if flag_name not in self.flags:
                    self.flags.append(flag_name)
                    self.dbg(f"  SET FLAG: {flag_name}")

            elif ac.startswith("REMOVE "):
                # Permanently remove from the game. start_room=-1 means
                # "in inventory" (see class docstring) - using that here
                # was a bug that silently teleported the object into the
                # player's pocket instead of removing it. -2 is a real
                # "gone" state that every room/inventory/HAS lookup
                # already ignores.
                obj_id = ac[7:].strip()
                if obj_id in self.game["objects"]:
                    self.game["objects"][obj_id]["start_room"] = -2
                    self.dbg(f"  REMOVED object {obj_id} (gone from game)")

            elif ac.startswith("MOVE TO "):
                # Teleport player
                try:
                    dest = int(ac[8:].strip())
                    self.current_room = dest
                    msgs.append(self.room_description())
                    self.dbg(f"  MOVED PLAYER to room {dest}")
                except ValueError:
                    pass

            elif ac.startswith("SCORE "):
                try:
                    pts = int(ac[6:].strip())
                    self.score = min(self.score + pts, self.max_score)
                    self.dbg(f"  SCORE +{pts} → {self.score}")
                except ValueError:
                    pass

            elif ac.startswith("MSG "):
                msg_key  = ac[4:].strip()
                msg_text = self.game.get("messages", {}).get(msg_key, "")
                if msg_text:
                    msgs.append(msg_text)
                    self.dbg(f"  MSG {msg_key} → '{msg_text}'")

            elif ac == "WINXXX":
                # Now implemented in advplay-c64-v3.bas too (prints the
                # response's message, then offers "play again y/n" and
                # either reloads+restarts or ends).
                self.win       = True
                self.game_over = True
                msgs.append(self.game.get("settings", {}).get("winmessage")
                            or "CONGRATULATIONS! YOU HAVE WON!")
                self.dbg("  GAME WON")

        return msgs

    # ------------------------------------------------------------------
    # Response matcher (BASIC lines 13300-13650)
    # ------------------------------------------------------------------

    def find_object(self, obj_word, candidates):
        """
        Match obj_word against a list of (oid, od) candidates.

        advplay-c64-v3.bas now stores the name field (previously
        discarded) and checks it as a second pass after the ID: LEFT$
        prefix against the ID first, then LEFT$ prefix against the full
        name. No word-splitting - "IRON" matches "IRON GATE" (name
        starts with it) but wouldn't match "OLD IRON GATE" (mid-string).
        """
        obj_word = obj_word.upper().strip()
        for oid, od in candidates:
            if oid.upper().startswith(obj_word):
                return oid, od
        for oid, od in candidates:
            if od.get("name", "").upper().startswith(obj_word):
                return oid, od
        return None, None

    def check_responses(self, c2):
        """
        Try every response whose command string is a SUBSTRING of c2.
        Return (message, extra_lines) for the first match whose condition passes.
        BASIC lines 13440-13500: substring search.
        """
        c2 = c2.upper()
        self.dbg(f"CHECK RESPONSES for: '{c2}'")

        for resp in self.game.get("responses", []):
            rc = resp.get("command", "").strip().upper()
            if not rc:
                continue

            # Substring match (BASIC line 13480)
            if rc not in c2:
                continue

            self.dbg(f"  RC '{rc}' found in '{c2}' — checking condition")

            cond = resp.get("condition", "").strip()
            if not self.check_condition(cond):
                self.dbg(f"  CONDITION FAILED: '{cond}'")
                continue

            # Match!  Show message, run action.
            message    = resp.get("message", "").strip()
            action_str = resp.get("action",  "").strip()
            extras     = self.execute_action(action_str)
            self.dbg(f"  MATCHED → msg='{message}' action='{action_str}'")
            return message, extras

        return None, []

    # ------------------------------------------------------------------
    # Main command handler
    # ------------------------------------------------------------------

    def expand_input(self, raw):
        """
        Expand the first word of input using vocabulary synonyms.
        e.g. "GET SWORD" → "TAKE SWORD" if TAKE=GET in vocabulary.
        Only the first word is expanded — keeps things predictable.
        """
        words = raw.strip().upper().split()
        if not words:
            return raw.strip().upper()

        for base, synonyms in self.game.get("vocabulary", {}).items():
            syns_upper = [s.strip().upper() for s in synonyms]
            if words[0] in syns_upper:
                self.dbg(f"VOCAB: '{words[0]}' → '{base.upper()}'")
                words[0] = base.upper()
                break

        # Filler words are dropped so phrasing can be natural, matching the
        # runtime's routine at 7200: "GIVE CHALICE TO WIZARD" and
        # "GIVE CHALICE WIZARD" reach the same response.
        kept = [words[0]] + [w for w in words[1:] if w not in FILLER_WORDS]
        if kept != words:
            self.dbg(f"FILLER: {' '.join(words)} → {' '.join(kept)}")
        return " ".join(kept)

    def execute_command(self, raw_input):
        """
        Process one line of player input.
        Returns (message_string, [extra_lines]).
        """
        c = self.expand_input(raw_input)
        self.dbg(f"INPUT: '{c}'")

        if not c:
            return "Pardon?", []

        # ---- QUIT ----
        if c in ("QUIT", "Q"):
            self.game_over = True
            return "Goodbye!", []

        # ---- SCORE ----
        if c == "SCORE":
            return f"Score: {self.score} of {self.max_score}", []

        # ---- LOOK / L ----
        if c in ("LOOK", "L"):
            return self.room_description(), []

        # ---- INVENTORY / I ----
        if c in ("INVENTORY", "INV", "I"):
            inv = self.inventory_objects()
            if not inv:
                return self.get_msg("INVENTORY_EMPTY", "You aren't carrying anything."), []
            names = ", ".join(od["name"] for _, od in inv)
            return f"You are carrying: {names}", []

        # ---- MOVEMENT: N S E W NORTH SOUTH EAST WEST ----
        dir_map = {
            "N": 0, "NORTH": 0,
            "S": 1, "SOUTH": 1,
            "E": 2, "EAST":  2,
            "W": 3, "WEST":  3,
        }
        move_word = c.split()[0] if c.split() else c
        # Handle "GO NORTH" etc.
        if move_word == "GO" and len(c.split()) > 1:
            move_word = c.split()[1]

        if move_word in dir_map:
            idx      = dir_map[move_word]
            room     = self.current_room_data()
            next_room = int(room["exits"][idx]) if room else 0
            if next_room > 0:
                self.current_room = next_room
                self.dbg(f"MOVED to room {next_room}")
                return self.room_description(), []
            else:
                return self.get_msg("CANT_GO", "You can't go that way."), []

        # ---- TAKE / GET ----
        if c.startswith("TAKE ") or c.startswith("GET "):
            obj_word = c[5:] if c.startswith("TAKE ") else c[4:]
            obj_word = obj_word.strip()
            oid, od = self.find_object(obj_word, self.room_objects())
            if od:
                if "TAKEABLE" in od.get("properties", "").upper():
                    od["start_room"] = -1
                    self.dbg(f"TOOK {oid}")
                    return self.get_msg("ITEM_TAKEN", "Taken."), []
                else:
                    return "You can't take that.", []
            return self.get_msg("NOT_HERE", "I don't see that here."), []

        # ---- DROP ----
        if c.startswith("DROP "):
            obj_word = c[5:].strip()
            oid, od = self.find_object(obj_word, self.inventory_objects())
            if od:
                od["start_room"] = self.current_room
                self.dbg(f"DROPPED {oid}")
                return self.get_msg("ITEM_DROPPED", "Dropped."), []
            return "You don't have that.", []

        # ---- EXAMINE / X ----
        if c.startswith("EXAMINE ") or c.startswith("X "):
            obj_word = c[8:].strip() if c.startswith("EXAMINE ") else c[2:].strip()
            # Check responses first (FIXED objects like GATE have custom examine text)
            msg, extras = self.check_responses(f"EXAMINE {obj_word}")
            if msg is not None:
                return msg, extras
            # Fall back to object description
            oid, od = self.find_object(obj_word, self.room_objects() + self.inventory_objects())
            if od:
                return od.get("description", "Nothing special."), []
            return self.get_msg("NOT_HERE", "I don't see that here."), []

        # ---- USE ----
        # BASIC line 5390: left$(c$,4)="use "
        if c.startswith("USE "):
            rest = c[4:].strip()
            for sep in (" ON ", " WITH ", " IN ", " AT "):
                if sep in rest:
                    parts = rest.split(sep, 1)
                    rest  = parts[0].strip() + " " + parts[1].strip()
                    break
            c2 = "USE " + rest
            msg, extras = self.check_responses(c2)
            if msg is not None:
                return msg, extras
            return "Nothing happens.", []

        # ---- GIVE ----
        if c.startswith("GIVE "):
            c2 = c
            msg, extras = self.check_responses(c2)
            if msg is not None:
                return msg, extras
            return self.get_msg("DONT_UNDERSTAND", "I don't understand that."), []

        # Any other verb gets one pass at the response table, matching the
        # runtime's line 5396. This is what lets TALK, HIT and any verb the
        # author invents work here as they now do on the C64.
        msg, extras = self.check_responses(c)
        if msg is not None:
            return msg, extras

        return self.get_msg("DONT_UNDERSTAND", "I don't understand that."), []

    # ------------------------------------------------------------------
    # Room description (BASIC lines 6000-6230)
    # ------------------------------------------------------------------

    def room_description(self):
        room = self.current_room_data()
        if not room:
            return "You are in a void."

        lines = [
            "",
            room["name"],
            "=" * 40,
            room.get("description", ""),
            "",
        ]

        # Objects in room. A HIDDEN object is present and can be examined or
        # used, but the room never announces it — matching the runtime's
        # line 6060, so a secret reads the same in the Player and on disk.
        here = [(oid, od) for oid, od in self.room_objects()
                if "HIDDEN" not in (od.get("properties") or "").upper()]
        if here:
            lines.append("You see: " + ", ".join(od["name"] for _, od in here))

        # Exits
        exit_names = ["NORTH", "SOUTH", "EAST", "WEST"]
        exits = [exit_names[i] for i, v in enumerate(room["exits"]) if int(v) > 0]
        lines.append("Exits: " + (", ".join(exits) if exits else "none"))

        return "\n".join(lines)

class AdventureEditor:
    def __init__(self, root):
        self.root = root
        self.root.title("C64 Adventure Maker")
        self.root.geometry("1200x800")
        
        # Game data
        self.game = {
            "settings": {"title": "New Adventure", "author": "", "version": "1.0", "startroom": 1, "maxscore": 100},
            "rooms": {"1": {"name": "Start", "description": "You are here.", "exits": [0, 0, 0, 0], "scene_id": None}},
            "objects": {},
            "vocabulary": {"NORTH": ["N"], "SOUTH": ["S"], "EAST": ["E"], "WEST": ["W"]},
            "messages": {},
            "responses": [],
            "scenes": {}   # {scene_id: {"name": str, "koala_b64": str}}
        }
        
        self.current_file = None
        self.game_engine = None
        self.map_positions = {}
        self._drag_data = {"id": None, "room_id": None, "x": 0, "y": 0}
        self._selected_map_room = None
        self._suppress_room_changes = False
        self._current_room_id = None

        # Scene UI state
        self._current_scene_id      = None       # scene selected in Scenes tab
        self._scene_preview_photo   = None       # Scenes-tab preview PhotoImage (keep ref!)

        self.setup_styles()
        self.create_ui()
        
    def setup_styles(self):
        """Claude-inspired dark theme — charcoal base, violet/orange/sage accents"""
        style = ttk.Style()
        style.theme_use('clam')

        # ── Fonts ────────────────────────────────────────────────
        font_face     = "Courier"   # font family used throughout

        font_xs       = (font_face, 9)               # debug log, map ID badge
        font_xs_bold  = (font_face, 9,  "bold")
        font_sm       = (font_face, 11)              # hints, LabelFrame labels
        font_sm_bold  = (font_face, 11, "bold")
        font_base     = (font_face, 12)              # player state values
        font_base_bold= (font_face, 12, "bold")      # player state labels
        font_md       = (font_face, 13)              # buttons, text areas
        font_md_bold  = (font_face, 13, "bold")      # tabs
        font_lg       = (font_face, 14)              # entries, listboxes, labels
        font_lg_bold  = (font_face, 14, "bold")
        font_xl_bold  = (font_face, 16, "bold")      # main section headers
        font_map_room = (font_face, 10)              # map room name text

        # ── Core backgrounds ─────────────────────────────────────
        bg_dark    = "#1c1c1e"   # main window background
        bg_mid     = "#242428"   # panels, LabelFrames, tab bar
        bg_light   = "#2a2a2e"   # default input field background
        bg_panel   = "#222226"   # side panels (player state)

        # ── Core foregrounds ─────────────────────────────────────
        fg_primary = "#d4d0c8"   # main body text
        fg_dim     = "#df932f"   # very muted — hints that recede
        fg_dark    = "#1c1c1e"   # text on bright backgrounds
        fg_hint    = "#df932f"   # section labels, format hints

        # ── Accent palette ───────────────────────────────────────
        accent     = "#c8c4bc"   # headers, selected tab text
        accent_dim = "#44424a"   # hover backgrounds
        teal       = "#4ec9b0"   # focus cursor, debug text, map selection
        orange     = "#f0883e"   # badges, inventory, score values
        sage       = "#7ec8a0"   # game output text
        blue_grey  = "#6b8aad"   # map one-way arrows
        violet     = "#a78bfa"   # text cursor in desc/vocab/responses
        violet_dim = "#3d3650"   # listbox selection background

        # ── Tab colors ───────────────────────────────────────────
        tab_fg         = "#0c7c7c"   # inactive tab text
        tab_fg_active  = "#1acde4"   # selected tab text

        # ── Button colors ────────────────────────────────────────
        btn_hover_bg   = "#3a3a40"   # button hover background
        btn_hover_fg   = "#e8a050"   # button hover text

        # ── Control chrome ───────────────────────────────────────
        # Borders and slider parts. These are deliberately high-luminance-
        # contrast against their own backgrounds rather than distinguished by
        # hue, so they stay visible with any color vision deficiency.
        border_col = "#7a7a85"   # 4.0:1 on bg_dark, 3.4:1 on bg_light — meets
                                 # WCAG 1.4.11 (3:1) for non-text UI controls
        trough_bg  = "#141416"   # slider trough — near black
        slider_fg  = "#e8e6e1"   # slider thumb — near white (~13:1 on trough)

        # ── ttk widget styles ────────────────────────────────────
        # Clam's default bevel colors are light grey (#eeebe7 / #9e9a91). They
        # are inherited by every widget and render as a bright frame around
        # dark fills — especially heavy on macOS. Override them at the root
        # style so nothing gets a light border by default.
        style.configure(".",
                        background=bg_dark,
                        foreground=fg_primary,
                        bordercolor=border_col,
                        lightcolor=bg_light,
                        darkcolor=bg_dark,
                        troughcolor=trough_bg,
                        focuscolor=teal)

        style.configure("TFrame",
                        background=bg_dark)

        # Crop-band slider. Previously unstyled, so it inherited clam's light
        # defaults: a #dcdad5 thumb on a #bab5ab trough is a 1.5:1 contrast
        # ratio — the thumb was invisible. Light thumb on a near-black trough
        # is ~13:1 and, being a luminance difference rather than a hue one,
        # stays legible with any form of color vision deficiency.
        style.configure("Band.Horizontal.TScale",
                        background=slider_fg,
                        troughcolor=trough_bg,
                        bordercolor=border_col,
                        lightcolor=slider_fg,
                        darkcolor=slider_fg,
                        borderwidth=1)

        style.map("Band.Horizontal.TScale",
                  background=[("active", teal), ("pressed", teal)],
                  lightcolor=[("active", teal), ("pressed", teal)],
                  darkcolor=[("active", teal), ("pressed", teal)])

        # Dropdowns (the room's Scene picker). ttk + clam draws these itself,
        # so they look the same on macOS as elsewhere; tk.Menubutton lets
        # Aqua override the colors and render a native light control.
        style.configure("Picker.TMenubutton",
                        background=bg_light,
                        foreground=fg_primary,
                        bordercolor=border_col,
                        lightcolor=bg_light,
                        darkcolor=bg_light,
                        arrowcolor=fg_hint,
                        borderwidth=1,
                        relief="solid",
                        padding=[8, 4],
                        font=font_md)

        style.map("Picker.TMenubutton",
                  background=[("active", btn_hover_bg)],
                  foreground=[("active", btn_hover_fg)],
                  bordercolor=[("active", teal)],
                  arrowcolor=[("active", btn_hover_fg)])

        style.configure("TLabelframe",
                        background=bg_mid,
                        bordercolor=bg_mid, relief="groove",
                        borderwidth=1, lightcolor=bg_mid, darkcolor=bg_mid)

        style.configure("TLabelframe.Label",
                        background=bg_mid,
                        foreground=fg_hint,
                        font=font_sm)

        style.configure("TLabel",
                        background=bg_dark,
                        foreground=fg_primary,
                        font=font_lg)

        style.configure("Header.TLabel",
                        background=bg_dark,
                        foreground=accent,
                        font=font_xl_bold)

        style.configure("TNotebook",
                        background=bg_dark,
                        borderwidth=0)

        style.configure("TNotebook.Tab",
                        background=bg_mid,
                        foreground=tab_fg,
                        font=font_md_bold,
                        padding=[12, 5])

        style.map("TNotebook.Tab",
                  background=[("selected", bg_dark)],
                  foreground=[("selected", tab_fg_active)])

        style.configure("TButton",
                        background=bg_light,
                        foreground=fg_primary,
                        font=font_md,
                        borderwidth=0,
                        relief="flat",
                        padding=[8, 4])

        style.map("TButton",
                  background=[("active", btn_hover_bg)],
                  foreground=[("active", btn_hover_fg)])

        style.configure("TEntry",
                        fieldbackground=bg_light,
                        foreground=fg_primary,
                        insertcolor=teal,
                        font=font_lg,
                        borderwidth=0,
                        relief="flat")

        style.map("TEntry",
                  bordercolor=[("focus", teal)],
                  lightcolor=[("focus", teal)],
                  darkcolor=[("focus", teal)])

        style.configure("TScrollbar",
                        background=bg_mid,
                        troughcolor=bg_dark,
                        borderwidth=0,
                        arrowcolor=fg_dim)

        # ── Color palette (widget-level access) ──────────────────
        self.colors = {
            # Global
            "bg_dark":          bg_dark,
            "bg_mid":           bg_mid,
            "bg_light":         bg_light,
            "bg_panel":         bg_panel,
            "fg_primary":       fg_primary,
            "fg_dim":           fg_dim,
            "fg_dark":          fg_dark,
            "fg_hint":          fg_hint,
            "fg_light":         fg_primary,
            "accent":           accent,
            "accent_dim":       accent_dim,
            "teal":             teal,
            "orange":           orange,
            "sage":             sage,
            "blue_grey":        blue_grey,
            "violet":           violet,
            "violet_dim":       violet_dim,
            "tab_fg":           tab_fg,
            "tab_fg_active":    tab_fg_active,
            "btn_hover_bg":     btn_hover_bg,
            "btn_hover_fg":     btn_hover_fg,

            # Settings bar
            "settings_entry_bg":    "#2a2a2e",
            "settings_entry_fg":    fg_primary,

            # Rooms tab
            # Control chrome (borders, slider parts)
            "border":               border_col,
            "trough_bg":            trough_bg,
            "slider_fg":            slider_fg,

            "room_list_bg":         "#252530",
            "room_list_fg":         fg_primary,
            "room_field_bg":        "#2a2a2e",
            "room_field_fg":        fg_primary,
            "room_desc_bg":         "#232328",
            "room_desc_fg":         fg_primary,
            "room_exit_bg":         "#2a2a2e",

            # Objects tab
            "obj_list_bg":          "#252530",
            "obj_list_fg":          fg_primary,
            "obj_field_bg":         "#2a2a2e",
            "obj_field_fg":         fg_primary,
            "obj_desc_bg":          "#232328",
            "obj_desc_fg":          fg_primary,

            # Vocabulary tab
            "vocab_bg":             "#232328",
            "vocab_fg":             fg_primary,

            # Messages tab
            "sysmsg_entry_bg":      "#2a2a2e",
            "sysmsg_entry_fg":      fg_primary,
            "custmsg_bg":           "#232328",
            "custmsg_fg":           fg_primary,

            # Responses tab
            "responses_bg":         "#232328",
            "responses_fg":         fg_primary,

            # Player tab
            "game_output_bg":       "#111113",
            "game_output_fg":       sage,
            "game_input_bg":        "#2a2a2e",
            "game_input_fg":        fg_primary,
            "inventory_bg":         "#242428",
            "inventory_fg":         orange,
            "debug_bg":             "#0f0f12",
            "debug_fg":             teal,
        }

        # ── Font palette (widget-level access) ───────────────────
        self.fonts = {
            "xs":        font_xs,         # (Courier, 9)  — debug log, map ID
            "xs_bold":   font_xs_bold,    # (Courier, 9, bold)
            "sm":        font_sm,         # (Courier, 11) — hints, section labels
            "sm_bold":   font_sm_bold,    # (Courier, 11, bold)
            "base":      font_base,       # (Courier, 12) — player state values
            "base_bold": font_base_bold,  # (Courier, 12, bold) — player state labels
            "md":        font_md,         # (Courier, 13) — buttons, text areas
            "md_bold":   font_md_bold,    # (Courier, 13, bold) — tabs
            "lg":        font_lg,         # (Courier, 14) — entries, listboxes
            "lg_bold":   font_lg_bold,    # (Courier, 14, bold)
            "xl_bold":   font_xl_bold,    # (Courier, 16, bold) — main headers
            "map_room":  font_map_room,   # (Courier, 10) — map room names
        }

        self.root.configure(bg=bg_dark)
    
    def create_ui(self):
        """Build main UI structure"""
        # Menu bar
        menubar = tk.Menu(self.root, bg=self.colors["bg_mid"], fg=self.colors["fg_primary"])
        self.root.config(menu=menubar)
        
        file_menu = tk.Menu(menubar, tearoff=0, bg=self.colors["bg_mid"], fg=self.colors["fg_primary"])
        menubar.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(label="New Game", command=self.new_game)
        file_menu.add_command(label="Open...", command=self.open_game)
        file_menu.add_command(label="Save", command=self.save_game)
        file_menu.add_command(label="Save As...", command=self.save_game_as)
        file_menu.add_separator()
        file_menu.add_command(label="Export .adv", command=self.export_adv)
        file_menu.add_command(label="Export & Build C64 Disk (graphical)...", command=self.export_and_build)
        file_menu.add_command(label="Export & Build C64 Disk (text only)...", command=self.export_and_build_text)
        file_menu.add_command(label="Export StoryTllr Project...", command=self.export_storytllr)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.root.quit)
        
        # Top section: Game settings
        settings_frame = ttk.Frame(self.root)
        settings_frame.pack(side=tk.TOP, fill=tk.X, padx=10, pady=10)
        
        ttk.Label(settings_frame, text="Game Settings", style="Header.TLabel").pack(side=tk.LEFT)
        
        ttk.Label(settings_frame, text="Title:").pack(side=tk.LEFT, padx=(20, 5))
        self.title_var = tk.StringVar(value=self.game["settings"]["title"])
        title_entry = tk.Entry(settings_frame, textvariable=self.title_var, width=30, bg=self.colors["settings_entry_bg"], fg=self.colors["settings_entry_fg"], insertbackground=self.colors["teal"], bd=0, relief="flat", highlightthickness=0)
        title_entry.pack(side=tk.LEFT, padx=(0, 20))
        title_entry.bind("<KeyRelease>", lambda e: self.update_setting("title", self.title_var.get()))
        
        ttk.Label(settings_frame, text="Author:").pack(side=tk.LEFT, padx=(0, 5))
        self.author_var = tk.StringVar(value=self.game["settings"]["author"])
        author_entry = tk.Entry(settings_frame, textvariable=self.author_var, width=20, bg=self.colors["settings_entry_bg"], fg=self.colors["settings_entry_fg"], insertbackground=self.colors["teal"], bd=0, relief="flat", highlightthickness=0)
        author_entry.pack(side=tk.LEFT, padx=(0, 20))
        author_entry.bind("<KeyRelease>", lambda e: self.update_setting("author", self.author_var.get()))

        ttk.Label(settings_frame, text="Start Room:").pack(side=tk.LEFT, padx=(0, 5))
        self.startroom_var = tk.StringVar(value=str(self.game["settings"].get("startroom", 1)))
        startroom_entry = tk.Entry(settings_frame, textvariable=self.startroom_var, width=4, bg=self.colors["settings_entry_bg"], fg=self.colors["settings_entry_fg"], insertbackground=self.colors["teal"], bd=0, relief="flat", highlightthickness=0)
        startroom_entry.pack(side=tk.LEFT, padx=(0, 20))
        startroom_entry.bind("<KeyRelease>", lambda e: self.update_setting(
            "startroom", self._int_field(self.startroom_var.get(),
                                         self.game["settings"].get("startroom", 1))))

        ttk.Label(settings_frame, text="Max Score:").pack(side=tk.LEFT, padx=(0, 5))
        self.maxscore_var = tk.StringVar(value=str(self.game["settings"].get("maxscore", 100)))
        maxscore_entry = tk.Entry(settings_frame, textvariable=self.maxscore_var, width=6, bg=self.colors["settings_entry_bg"], fg=self.colors["settings_entry_fg"], insertbackground=self.colors["teal"], bd=0, relief="flat", highlightthickness=0)
        maxscore_entry.pack(side=tk.LEFT)
        maxscore_entry.bind("<KeyRelease>", lambda e: self.update_setting(
            "maxscore", self._int_field(self.maxscore_var.get(),
                                        self.game["settings"].get("maxscore", 100))))

        # Win text is one game-wide string, not a message-table entry: the
        # text engine reads it from [SETTINGS] and the graphical build inlines
        # it into the win block.
        win_frame = ttk.Frame(self.root)
        win_frame.pack(side=tk.TOP, fill=tk.X, padx=10, pady=(0, 8))
        ttk.Label(win_frame, text="Win Message:").pack(side=tk.LEFT, padx=(0, 5))
        self.winmessage_var = tk.StringVar(
            value=self.game["settings"].get("winmessage", ""))
        win_entry = tk.Entry(
            win_frame, textvariable=self.winmessage_var,
            bg=self.colors["settings_entry_bg"], fg=self.colors["settings_entry_fg"],
            insertbackground=self.colors["teal"], bd=0, relief="flat",
            highlightthickness=0)
        win_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6))
        win_entry.bind("<KeyRelease>",
                       lambda e: self.update_setting("winmessage",
                                                     self.winmessage_var.get()))
        ttk.Label(win_frame, text="(shown when a response carries the WIN action)",
                  foreground=self.colors["fg_dim"]).pack(side=tk.LEFT)

        # Notebook for tabs
        notebook = ttk.Notebook(self.root)
        notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        self.notebook = notebook

        # Map tab
        self.map_tab = ttk.Frame(notebook)
        notebook.add(self.map_tab, text="🗺 Map")
        self.create_map_tab()
        
        # Rooms tab
        self.rooms_tab = ttk.Frame(notebook)
        notebook.add(self.rooms_tab, text="Rooms")
        self.create_rooms_tab()
        
        # Scenes tab
        self.scenes_tab = ttk.Frame(notebook)
        notebook.add(self.scenes_tab, text="🎨 Scenes")
        self.create_scenes_tab()

        # Objects tab
        self.objects_tab = ttk.Frame(notebook)
        notebook.add(self.objects_tab, text="Objects")
        self.create_objects_tab()
        
        # Vocabulary tab
        self.vocab_tab = ttk.Frame(notebook)
        notebook.add(self.vocab_tab, text="Vocabulary")
        self.create_vocab_tab()
        
        # Messages tab
        self.messages_tab = ttk.Frame(notebook)
        notebook.add(self.messages_tab, text="Messages")
        self.create_messages_tab()
        
        # Responses tab
        self.responses_tab = ttk.Frame(notebook)
        notebook.add(self.responses_tab, text="Responses")
        self.create_responses_tab()
        
        # Player tab
        self.player_tab = ttk.Frame(notebook)
        notebook.add(self.player_tab, text="▶ Player")
        self.create_player_tab()
    
        # Map node positions {room_id_str: (x, y)}
        # (initialised in __init__)

    def create_map_tab(self):
        """Graphical map editor"""
        # Toolbar
        toolbar = ttk.Frame(self.map_tab)
        toolbar.pack(side=tk.TOP, fill=tk.X, padx=5, pady=5)
        ttk.Label(toolbar, text="Room Map", style="Header.TLabel").pack(side=tk.LEFT)
        ttk.Button(toolbar, text="Auto Layout", command=self.map_auto_layout).pack(side=tk.LEFT, padx=10)
        ttk.Button(toolbar, text="Refresh", command=self.refresh_map).pack(side=tk.LEFT, padx=2)

        # Canvas with scrollbars
        canvas_frame = ttk.Frame(self.map_tab)
        canvas_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        h_scroll = ttk.Scrollbar(canvas_frame, orient=tk.HORIZONTAL)
        h_scroll.pack(side=tk.BOTTOM, fill=tk.X)
        v_scroll = ttk.Scrollbar(canvas_frame, orient=tk.VERTICAL)
        v_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        self.map_canvas = tk.Canvas(
            canvas_frame,
            bg="#111113",
            scrollregion=(0, 0, 2000, 2000),
            xscrollcommand=h_scroll.set,
            yscrollcommand=v_scroll.set,
        )
        self.map_canvas.pack(fill=tk.BOTH, expand=True)
        h_scroll.config(command=self.map_canvas.xview)
        v_scroll.config(command=self.map_canvas.yview)

        # Bind drag events
        self.map_canvas.bind("<ButtonPress-1>",   self.map_on_press)
        self.map_canvas.bind("<B1-Motion>",        self.map_on_drag)
        self.map_canvas.bind("<ButtonRelease-1>",  self.map_on_release)

    # ------------------------------------------------------------------
    # Map rendering
    # ------------------------------------------------------------------

    BOX_W  = 130
    BOX_H  = 50
    BOX_PAD = 20   # padding inside box

    def map_auto_layout(self):
        """
        Direction-aware BFS layout: places each room in the compass
        direction of its exit so N/S runs vertically, E/W horizontally.
        """
        rooms = self.game["rooms"]
        if not rooms:
            return

        gap_x = self.BOX_W + 90
        gap_y = self.BOX_H + 80
        # col_delta, row_delta for N S E W
        dir_delta = {0: (0, -1), 1: (0, 1), 2: (1, 0), 3: (-1, 0)}

        start_id = str(self.game["settings"].get("startroom", 1))
        if start_id not in rooms:
            start_id = sorted(rooms.keys(), key=lambda k: int(k) if k.isdigit() else 999)[0]

        grid  = {}              # (col, row) -> room_id
        pos   = {}              # room_id -> (col, row)
        queue = [start_id]
        pos[start_id]  = (0, 0)
        grid[(0, 0)]   = start_id
        visited = {start_id}

        while queue:
            rid = queue.pop(0)
            col, row = pos[rid]
            for idx, dest in enumerate(rooms[rid]["exits"]):
                dest_str = str(dest)
                if int(dest) <= 0 or dest_str not in rooms or dest_str in visited:
                    continue
                dc, dr = dir_delta[idx]
                nc, nr = col + dc, row + dr
                # Nudge right until the cell is free
                while (nc, nr) in grid:
                    nc += 1
                grid[(nc, nr)] = dest_str
                pos[dest_str]  = (nc, nr)
                visited.add(dest_str)
                queue.append(dest_str)

        # Orphan rooms not reachable from start
        max_col = max((c for c, r in grid), default=0)
        orphan_row = 0
        for rid in rooms:
            if rid not in pos:
                max_col += 1
                grid[(max_col, orphan_row)] = rid
                pos[rid] = (max_col, orphan_row)
                orphan_row += 1

        min_col = min(c for c, r in grid)
        min_row = min(r for c, r in grid)
        origin_x, origin_y = 80, 80

        self.map_positions = {}
        for rid, (col, row) in pos.items():
            self.map_positions[rid] = (
                origin_x + (col - min_col) * gap_x,
                origin_y + (row - min_row) * gap_y,
            )
        self.refresh_map()

    def refresh_map(self):
        """Redraw the entire map canvas."""
        c = self.map_canvas
        c.delete("all")

        rooms = self.game["rooms"]

        # Auto-layout any rooms not yet positioned
        if not self.map_positions:
            self.map_auto_layout()
            return  # auto_layout calls refresh_map itself

        for rid, room in rooms.items():
            if rid not in self.map_positions:
                # New room added since last layout — park it somewhere visible
                taken_xs = [p[0] for p in self.map_positions.values()]
                self.map_positions[rid] = (max(taken_xs, default=60) + self.BOX_W + 80, 60)

        # Draw exit arrows first (behind boxes)
        dir_names  = ["NORTH", "SOUTH", "EAST", "WEST"]
        dir_offset = {           # where on the box edge the arrow starts/ends
            "NORTH": (self.BOX_W // 2,  0),
            "SOUTH": (self.BOX_W // 2,  self.BOX_H),
            "EAST":  (self.BOX_W,        self.BOX_H // 2),
            "WEST":  (0,                 self.BOX_H // 2),
        }
        drawn_pairs = set()

        for rid, room in rooms.items():
            x1, y1 = self.map_positions.get(rid, (0, 0))
            for idx, dest in enumerate(room["exits"]):
                dest_str = str(dest)
                if int(dest) <= 0 or dest_str not in rooms:
                    continue

                pair = tuple(sorted([rid, dest_str]))
                is_two_way = str(rooms[dest_str]["exits"][ [1,0,3,2][idx] ]) == rid

                dx, dy = dir_offset[dir_names[idx]]
                sx, sy = x1 + dx, y1 + dy

                x2, y2 = self.map_positions.get(dest_str, (0, 0))
                # Arrive at the opposite edge of the destination box
                opp_dir = dir_names[[1, 0, 3, 2][idx]]
                ex, ey  = dir_offset[opp_dir]
                tx, ty  = x2 + ex, y2 + ey

                if is_two_way and pair in drawn_pairs:
                    continue
                drawn_pairs.add(pair)

                color = self.colors["teal"] if is_two_way else self.colors["orange"]
                c.create_line(sx, sy, tx, ty,
                              fill=color, width=2,
                              arrow=tk.LAST if not is_two_way else tk.NONE,
                              smooth=True, tags="arrow")

        # Draw room boxes
        for rid, room in rooms.items():
            x, y = self.map_positions.get(rid, (0, 0))
            selected = (rid == self._selected_map_room)
            self._draw_room_box(rid, room, x, y, selected)

    def _draw_room_box(self, rid, room, x, y, selected=False):
        c      = self.map_canvas
        bg     = self.colors["bg_light"]
        border = self.colors["teal"] if selected else self.colors["bg_light"]
        fg     = self.colors["fg_light"]
        width  = 3 if selected else 1

        # Box
        c.create_rectangle(x, y, x + self.BOX_W, y + self.BOX_H,
                           fill=self.colors["bg_mid"], outline=border, width=width,
                           tags=("room", f"room_{rid}"))
        # Room ID badge
        c.create_text(x + 8, y + 8,
                      text=rid, anchor=tk.NW,
                      fill=self.colors["accent"],
                      font=self.fonts["xs_bold"],
                      tags=("room", f"room_{rid}"))
        # Room name (truncated)
        name = room.get("name", "")
        if len(name) > 14:
            name = name[:13] + "…"
        c.create_text(x + self.BOX_W // 2, y + self.BOX_H // 2 + 4,
                      text=name, anchor=tk.CENTER,
                      fill=self.colors["fg_primary"], font=self.fonts["map_room"],
                      tags=("room", f"room_{rid}"))

    # ------------------------------------------------------------------
    # Map interaction — drag to reposition, click to select
    # ------------------------------------------------------------------

    def _room_at(self, cx, cy):
        """Return room_id string for the box under canvas coords (cx,cy), or None."""
        for rid, (x, y) in self.map_positions.items():
            if x <= cx <= x + self.BOX_W and y <= cy <= y + self.BOX_H:
                return rid
        return None

    def map_on_press(self, event):
        cx = self.map_canvas.canvasx(event.x)
        cy = self.map_canvas.canvasy(event.y)
        rid = self._room_at(cx, cy)
        self._drag_data = {"room_id": rid, "x": cx, "y": cy, "moved": False}
        if rid:
            self._selected_map_room = rid
            self.refresh_map()

    def map_on_drag(self, event):
        rid = self._drag_data.get("room_id")
        if not rid:
            return
        cx = self.map_canvas.canvasx(event.x)
        cy = self.map_canvas.canvasy(event.y)
        dx = cx - self._drag_data["x"]
        dy = cy - self._drag_data["y"]
        if abs(dx) > 2 or abs(dy) > 2:
            self._drag_data["moved"] = True
        ox, oy = self.map_positions.get(rid, (0, 0))
        self.map_positions[rid] = (ox + dx, oy + dy)
        self._drag_data["x"] = cx
        self._drag_data["y"] = cy
        self.refresh_map()

    def map_on_release(self, event):
        rid  = self._drag_data.get("room_id")
        moved = self._drag_data.get("moved", False)
        self._drag_data = {"room_id": None, "x": 0, "y": 0, "moved": False}
        # Only switch to editor on a clean click, not after a drag
        if rid and not moved:
            self.select_room_in_editor(rid)

    def select_room_in_editor(self, room_id_str):
        """Select room in the Rooms tab list and populate detail fields."""
        # Switch to Rooms tab
        self.notebook.select(1)  # index 1 = Rooms tab (Map is 0)

        # Select in listbox
        for i in range(self.rooms_listbox.size()):
            entry = self.rooms_listbox.get(i)
            if entry.split(":")[0].strip() == room_id_str:
                self.rooms_listbox.selection_clear(0, tk.END)
                self.rooms_listbox.selection_set(i)
                self.rooms_listbox.see(i)
                break

        # Populate fields directly
        room = self.game["rooms"].get(room_id_str)
        if not room:
            return
        self._current_room_id = room_id_str
        self._suppress_room_changes = True
        self.room_id_var.set(room_id_str)
        self.room_name_var.set(room.get("name", ""))
        self.room_desc_text.delete(1.0, tk.END)
        self.room_desc_text.insert(1.0, room.get("description", ""))
        self.room_exit_n.set(str(room.get("exits", [0,0,0,0])[0]))
        self.room_exit_s.set(str(room.get("exits", [0,0,0,0])[1]))
        self.room_exit_e.set(str(room.get("exits", [0,0,0,0])[2]))
        self.room_exit_w.set(str(room.get("exits", [0,0,0,0])[3]))

        sid = room.get("scene_id")
        self.room_scene_id = sid if sid and sid in self.game.get("scenes", {}) else None
        if self.room_scene_id is None:
            self.room_scene_display_var.set("(none)")
        else:
            name = self.game["scenes"][self.room_scene_id].get("name", "")
            self.room_scene_display_var.set(
                f"{self.room_scene_id}   {name}" if name else self.room_scene_id
            )
        self._suppress_room_changes = False

    def create_rooms_tab(self):
        """Room editor UI"""
        left_frame = ttk.Frame(self.rooms_tab)
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=False, padx=5, pady=5)
        
        ttk.Label(left_frame, text="Rooms", style="Header.TLabel").pack()
        self._capacity_label(left_frame, "rooms", anchor=tk.W, pady=(2, 0))

        listbox_frame = ttk.Frame(left_frame)
        listbox_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        
        scrollbar = ttk.Scrollbar(listbox_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.rooms_listbox = tk.Listbox(listbox_frame, yscrollcommand=scrollbar.set, 
                                        bg=self.colors["room_list_bg"], fg=self.colors["room_list_fg"],
                                        font=self.fonts["lg"], selectbackground=self.colors["violet_dim"], selectforeground="#ffffff",
                                        relief=tk.FLAT, bd=0, highlightthickness=0,)
        self.rooms_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=self.rooms_listbox.yview)
        self.rooms_listbox.bind("<<ListboxSelect>>", self.on_room_selected)
        
        button_frame = ttk.Frame(left_frame)
        button_frame.pack(fill=tk.X, pady=5)
        ttk.Button(button_frame, text="+ New", command=self.add_room).pack(side=tk.LEFT, padx=2)
        ttk.Button(button_frame, text="- Delete", command=self.delete_room).pack(side=tk.LEFT, padx=2)
        
        right_frame = ttk.Frame(self.rooms_tab)
        right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        ttk.Label(right_frame, text="Room Details", style="Header.TLabel").pack()
        
        id_frame = ttk.Frame(right_frame)
        id_frame.pack(fill=tk.X, pady=5)
        ttk.Label(id_frame, text="ID:").pack(side=tk.LEFT, padx=5)
        self.room_id_var = tk.StringVar()
        tk.Entry(id_frame, textvariable=self.room_id_var, width=5, bg=self.colors["room_field_bg"], fg=self.colors["room_field_fg"], insertbackground=self.colors["teal"], bd=0, relief="flat", highlightthickness=0).pack(side=tk.LEFT)
        
        name_frame = ttk.Frame(right_frame)
        name_frame.pack(fill=tk.X, pady=5)
        ttk.Label(name_frame, text="Name:").pack(side=tk.LEFT, padx=5)
        self.room_name_var = tk.StringVar()
        tk.Entry(name_frame, textvariable=self.room_name_var, width=40, bg=self.colors["room_field_bg"], fg=self.colors["room_field_fg"], insertbackground=self.colors["teal"], bd=0, relief="flat", highlightthickness=0).pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.room_name_var.trace("w", self.on_room_changed)
        
        ttk.Label(right_frame, text="Description:").pack(anchor=tk.W, padx=5, pady=(10, 0))
        self.room_desc_text = tk.Text(right_frame, height=6, width=50, 
                                      bg=self.colors["room_desc_bg"], fg=self.colors["room_desc_fg"],
                                      font=self.fonts["md"], insertbackground=self.colors["violet"], wrap=tk.WORD,
                                      relief=tk.FLAT, bd=0, highlightthickness=0,)
        self.room_desc_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.room_desc_text.bind("<KeyRelease>", self.on_room_changed)
        
        exits_frame = tk.LabelFrame(right_frame, text="Exits (0=none)", bg=self.colors["bg_mid"], fg=self.colors["fg_hint"], font=self.fonts["sm"], bd=0, relief="flat", highlightthickness=0, padx=5, pady=5)
        exits_frame.pack(fill=tk.X, padx=5, pady=5)
        
        exits_inner = ttk.Frame(exits_frame)
        exits_inner.pack(fill=tk.X)
        
        ttk.Label(exits_inner, text="N:").pack(side=tk.LEFT, padx=2)
        self.room_exit_n = tk.StringVar()
        tk.Entry(exits_inner, textvariable=self.room_exit_n, width=3, bg=self.colors["room_exit_bg"], fg=self.colors["room_field_fg"], insertbackground=self.colors["teal"], bd=0, relief="flat", highlightthickness=0).pack(side=tk.LEFT, padx=2)
        self.room_exit_n.trace("w", self.on_room_changed)
        
        ttk.Label(exits_inner, text="S:").pack(side=tk.LEFT, padx=2)
        self.room_exit_s = tk.StringVar()
        tk.Entry(exits_inner, textvariable=self.room_exit_s, width=3, bg=self.colors["room_exit_bg"], fg=self.colors["room_field_fg"], insertbackground=self.colors["teal"], bd=0, relief="flat", highlightthickness=0).pack(side=tk.LEFT, padx=2)
        self.room_exit_s.trace("w", self.on_room_changed)
        
        ttk.Label(exits_inner, text="E:").pack(side=tk.LEFT, padx=2)
        self.room_exit_e = tk.StringVar()
        tk.Entry(exits_inner, textvariable=self.room_exit_e, width=3, bg=self.colors["room_exit_bg"], fg=self.colors["room_field_fg"], insertbackground=self.colors["teal"], bd=0, relief="flat", highlightthickness=0).pack(side=tk.LEFT, padx=2)
        self.room_exit_e.trace("w", self.on_room_changed)
        
        ttk.Label(exits_inner, text="W:").pack(side=tk.LEFT, padx=2)
        self.room_exit_w = tk.StringVar()
        tk.Entry(exits_inner, textvariable=self.room_exit_w, width=3, bg=self.colors["room_exit_bg"], fg=self.colors["room_field_fg"], insertbackground=self.colors["teal"], bd=0, relief="flat", highlightthickness=0).pack(side=tk.LEFT, padx=2)
        self.room_exit_w.trace("w", self.on_room_changed)

        # Scene selector
        scene_frame = tk.LabelFrame(right_frame, text="Scene  (graphic shown when player enters this room)",
                                    bg=self.colors["bg_mid"], fg=self.colors["fg_hint"], font=self.fonts["sm"],
                                    bd=0, relief="flat", highlightthickness=0, padx=5, pady=5)
        scene_frame.pack(fill=tk.X, padx=5, pady=5)

        self.room_scene_display_var = tk.StringVar(value="(none)")
        self.room_scene_id          = None   # actual scene id (or None), NOT trace-bound

        # ttk (clam) rather than tk.Menubutton: on macOS the Aqua theme
        # ignores a tk.Menubutton's bg/fg and draws a native light control,
        # which is unreadable inside this dark UI. clam draws it itself, so
        # the styling below applies on every platform.
        self.room_scene_menubutton = ttk.Menubutton(
            scene_frame,
            textvariable=self.room_scene_display_var,
            style="Picker.TMenubutton",
            direction="below",
            width=32,
        )
        self.room_scene_menubutton.pack(side=tk.LEFT, fill=tk.X, expand=True)

        self._room_scene_menu = tk.Menu(
            self.room_scene_menubutton, tearoff=0,
            bg=self.colors["bg_mid"], fg=self.colors["fg_primary"],
            activebackground=self.colors["violet_dim"], activeforeground="#ffffff",
            bd=0,
        )
        # postcommand rebuilds the menu each time it's opened, so newly-imported
        # scenes appear without any explicit refresh call from other tabs.
        self._room_scene_menu.configure(postcommand=self._rebuild_room_scene_menu)
        self.room_scene_menubutton.configure(menu=self._room_scene_menu)

        self.refresh_rooms_list()
    
    def _rebuild_room_scene_menu(self):
        """Populate the scene dropdown from the current scenes dict."""
        m = self._room_scene_menu
        m.delete(0, tk.END)
        m.add_command(label="(none)", command=lambda: self._set_current_room_scene(None))
        m.add_separator()
        scenes = self.game.get("scenes", {})
        for sid in sorted(scenes.keys()):
            name = scenes[sid].get("name", "")
            label = f"{sid}   {name}" if name else sid
            m.add_command(label=label, command=lambda s=sid: self._set_current_room_scene(s))
        if not scenes:
            m.add_command(label="(no scenes yet — import in Scenes tab)", state=tk.DISABLED)

    def _set_current_room_scene(self, scene_id):
        """Called when user picks a scene from the room's dropdown."""
        self.room_scene_id = scene_id
        if scene_id is None:
            self.room_scene_display_var.set("(none)")
        else:
            name = self.game.get("scenes", {}).get(scene_id, {}).get("name", "")
            self.room_scene_display_var.set(f"{scene_id}   {name}" if name else scene_id)
        # Persist to the room record
        self.on_room_changed()

    # ------------------------------------------------------------------
    # Scenes tab — import/manage C64 Koala multicolor bitmap graphics
    # ------------------------------------------------------------------

    # Preview size in the Scenes tab. Koala native is 160×200; C64 multicolor
    # pixels are 2:1 wide, so any correct scaling needs x_scale = 2 × y_scale.
    # At 4×2 we render 640×400 — big enough that dithering reads as texture,
    # not noise (small previews make Koala look noisier than it actually is).
    SCENE_PREVIEW_X_SCALE = 4
    SCENE_PREVIEW_Y_SCALE = 2

    def create_scenes_tab(self):
        """Scenes editor: import Koala files, name them, preview, delete."""
        # Left: scene list + import/delete buttons
        left_frame = ttk.Frame(self.scenes_tab)
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=False, padx=5, pady=5)

        ttk.Label(left_frame, text="Scenes", style="Header.TLabel").pack()
        tk.Label(left_frame,
                 text="Graphical builds only.\nThe text (.adv) build has no\n"
                      "way to show pictures, so\nscenes are ignored there.",
                 bg=self.colors["bg_dark"], fg=self.colors["fg_hint"],
                 font=self.fonts["sm"], anchor=tk.W, justify=tk.LEFT
                 ).pack(anchor=tk.W, pady=(2, 4))

        listbox_frame = ttk.Frame(left_frame)
        listbox_frame.pack(fill=tk.BOTH, expand=True, pady=5)

        scrollbar = ttk.Scrollbar(listbox_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.scenes_listbox = tk.Listbox(
            listbox_frame, yscrollcommand=scrollbar.set,
            bg=self.colors["room_list_bg"], fg=self.colors["room_list_fg"],
            font=self.fonts["lg"],
            selectbackground=self.colors["violet_dim"], selectforeground="#ffffff",
            relief=tk.FLAT, bd=0, highlightthickness=0, width=24,
        )
        self.scenes_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=self.scenes_listbox.yview)
        self.scenes_listbox.bind("<<ListboxSelect>>", self.on_scene_selected)

        button_frame = ttk.Frame(left_frame)
        button_frame.pack(fill=tk.X, pady=5)
        ttk.Button(button_frame, text="+ Import Koala…", command=self.import_scene).pack(side=tk.LEFT, padx=2)
        ttk.Button(button_frame, text="- Delete", command=self.delete_scene).pack(side=tk.LEFT, padx=2)

        # Right: scene details + preview
        right_frame = ttk.Frame(self.scenes_tab)
        right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=5, pady=5)

        ttk.Label(right_frame, text="Scene Details", style="Header.TLabel").pack()

        id_frame = ttk.Frame(right_frame)
        id_frame.pack(fill=tk.X, pady=5)
        ttk.Label(id_frame, text="ID:").pack(side=tk.LEFT, padx=5)
        self.scene_id_var = tk.StringVar()
        tk.Entry(id_frame, textvariable=self.scene_id_var, width=20,
                 bg=self.colors["room_field_bg"], fg=self.colors["room_field_fg"],
                 insertbackground=self.colors["teal"],
                 bd=0, relief="flat", highlightthickness=0).pack(side=tk.LEFT)
        # Note: scene_id is the immutable dict key; we don't trace changes to
        # rename in-place (would need to touch every room that references it).
        # For now, ID is set at import time. Users can delete and re-import.

        name_frame = ttk.Frame(right_frame)
        name_frame.pack(fill=tk.X, pady=5)
        ttk.Label(name_frame, text="Name:").pack(side=tk.LEFT, padx=5)
        self.scene_name_var = tk.StringVar()
        tk.Entry(name_frame, textvariable=self.scene_name_var, width=40,
                 bg=self.colors["room_field_bg"], fg=self.colors["room_field_fg"],
                 insertbackground=self.colors["teal"],
                 bd=0, relief="flat", highlightthickness=0).pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.scene_name_var.trace("w", self.on_scene_name_changed)

        # Preview area — fixed size, matches what will render in the Player
        preview_w = 160 * self.SCENE_PREVIEW_X_SCALE
        preview_h = 200 * self.SCENE_PREVIEW_Y_SCALE

        preview_frame = tk.LabelFrame(
            right_frame,
            text=(f"Preview  (native C64 160×200 at {preview_w}×{preview_h}) — "
                  f"only the bright {CROP_ROWS}-row band reaches the C64"),
            bg=self.colors["bg_mid"], fg=self.colors["fg_hint"], font=self.fonts["sm"],
            bd=0, relief="flat", highlightthickness=0, padx=10, pady=10,
        )
        preview_frame.pack(fill=tk.BOTH, expand=True, pady=10)

        self.scene_preview_label = tk.Label(
            preview_frame,
            bg="#000000",  # black backdrop so unset preview looks intentional
            fg=self.colors["fg_dim"],
            text="(select a scene to preview)",
            width=preview_w, height=preview_h,
            bd=0, relief="flat", highlightthickness=0,
        )
        # Fixed pixel size — don't let it expand/shrink; images look sharpest
        # at their intended pixel dimensions.
        self.scene_preview_label.pack(pady=5)

        # Crop band control — the C64 shows only CROP_ROWS of the 200 rows,
        # so this picks which ones. Without it the export silently took the
        # top 96 rows while this preview showed all 200.
        crop_frame = ttk.Frame(right_frame)
        crop_frame.pack(fill=tk.X, pady=(8, 0))
        ttk.Label(crop_frame, text="Visible band:").pack(side=tk.LEFT, padx=5)

        self.scene_crop_var = tk.IntVar(value=CROP_CENTERED)
        self.scene_crop_scale = ttk.Scale(
            crop_frame, from_=0, to=CROP_MAX, orient=tk.HORIZONTAL,
            style="Band.Horizontal.TScale",
            command=self.on_scene_crop_changed,
        )
        self.scene_crop_scale.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)

        self.scene_crop_label_var = tk.StringVar(value="")
        tk.Label(
            crop_frame, textvariable=self.scene_crop_label_var,
            bg=self.colors["bg_dark"], fg=self.colors["fg_hint"],
            font=self.fonts["sm"], width=22, anchor=tk.W,
        ).pack(side=tk.LEFT, padx=5)

        ttk.Button(crop_frame, text="Center",
                   command=self.center_scene_crop).pack(side=tk.LEFT, padx=2)

        # Small "used by" hint
        self.scene_usage_var = tk.StringVar(value="")
        tk.Label(
            right_frame, textvariable=self.scene_usage_var,
            bg=self.colors["bg_dark"], fg=self.colors["fg_hint"],
            font=self.fonts["sm"], anchor=tk.W, justify=tk.LEFT,
        ).pack(fill=tk.X, padx=5, pady=(4, 0))

        self.refresh_scenes_list()

    def refresh_scenes_list(self):
        """Rebuild the scenes listbox from game data."""
        if not hasattr(self, "scenes_listbox"):
            return
        self.scenes_listbox.delete(0, tk.END)
        for sid in sorted(self.game.get("scenes", {}).keys()):
            name = self.game["scenes"][sid].get("name", "")
            label = f"{sid}: {name}" if name else sid
            self.scenes_listbox.insert(tk.END, label)

    def on_scene_selected(self, event):
        selection = self.scenes_listbox.curselection()
        if not selection:
            return
        entry = self.scenes_listbox.get(selection[0])
        sid = entry.split(":", 1)[0].strip()
        if sid not in self.game.get("scenes", {}):
            return
        self._current_scene_id = sid
        sdata = self.game["scenes"][sid]
        self.scene_id_var.set(sid)
        self.scene_name_var.set(sdata.get("name", ""))
        self._load_scene_crop(sdata)
        self._render_scene_preview(sdata.get("koala_b64", ""))
        self._update_scene_usage_hint(sid)

    def _scene_crop(self, sdata):
        """The crop offset for a scene, defaulting as the converter does."""
        return normalize_crop_offset(
            sdata.get("crop_offset", STORYTLLR_CROP_OFFSET))

    def _load_scene_crop(self, sdata):
        """Sync the slider to the selected scene without firing a re-render."""
        offset = self._scene_crop(sdata)
        self._suspend_crop_trace = True
        try:
            self.scene_crop_scale.set(offset)
            self.scene_crop_var.set(offset)
        finally:
            self._suspend_crop_trace = False
        self._update_crop_label(offset)

    def _update_crop_label(self, offset):
        last = offset + CROP_ROWS - 1
        self.scene_crop_label_var.set(f"rows {offset}-{last} of 200")

    def on_scene_crop_changed(self, value):
        """Slider moved: snap to a legal band, store it, re-render."""
        if getattr(self, "_suspend_crop_trace", False):
            return
        sid = getattr(self, "_current_scene_id", None)
        if not sid or sid not in self.game.get("scenes", {}):
            return
        offset = normalize_crop_offset(float(value))
        if offset == self.scene_crop_var.get():
            return                      # snapped back onto the same band
        self.scene_crop_var.set(offset)
        self.game["scenes"][sid]["crop_offset"] = offset
        self._update_crop_label(offset)
        self._render_scene_preview(self.game["scenes"][sid].get("koala_b64", ""))

    def center_scene_crop(self):
        """Reset the band to the middle of the image."""
        sid = getattr(self, "_current_scene_id", None)
        if not sid or sid not in self.game.get("scenes", {}):
            messagebox.showinfo("Visible band", "Please select a scene first.")
            return
        self.game["scenes"][sid]["crop_offset"] = CROP_CENTERED
        self._load_scene_crop(self.game["scenes"][sid])
        self._render_scene_preview(self.game["scenes"][sid].get("koala_b64", ""))

    def _render_scene_preview(self, koala_b64):
        """Decode and display a Koala scene in the Scenes-tab preview area.

        Rows outside the band that reaches the C64 are dimmed, so the preview
        matches the built disk instead of showing all 200 source rows.
        """
        if not koala_b64:
            self.scene_preview_label.config(image="", text="(no image data)")
            self._scene_preview_photo = None
            return
        try:
            raw = base64.b64decode(koala_b64)
            photo = make_scene_photo(
                raw,
                x_scale=self.SCENE_PREVIEW_X_SCALE,
                y_scale=self.SCENE_PREVIEW_Y_SCALE,
                crop_offset=self.scene_crop_var.get(),
            )
        except Exception as e:
            self.scene_preview_label.config(image="", text=f"(error: {e})")
            self._scene_preview_photo = None
            return
        # Keep a reference or Tk garbage-collects it and the image goes blank.
        self._scene_preview_photo = photo
        self.scene_preview_label.config(image=photo, text="")

    def _update_scene_usage_hint(self, sid):
        """Show a small hint listing which rooms use this scene."""
        used_by = []
        for rid, room in self.game.get("rooms", {}).items():
            if room.get("scene_id") == sid:
                used_by.append(f"{rid} ({room.get('name', '?')})")
        if used_by:
            self.scene_usage_var.set("Used by: " + ", ".join(used_by))
        else:
            self.scene_usage_var.set("Not yet attached to any room.")

    def on_scene_name_changed(self, *args):
        sid = getattr(self, "_current_scene_id", None)
        if not sid or sid not in self.game.get("scenes", {}):
            return
        self.game["scenes"][sid]["name"] = self.scene_name_var.get()
        self.refresh_scenes_list()

    def import_scene(self):
        """Prompt for a Koala file and add it to the scenes dict."""
        # Defer dialog per macOS stability pattern used elsewhere in the app
        self.root.after(100, self._do_import_scene)

    def _do_import_scene(self):
        path = filedialog.askopenfilename(
            title="Import Koala image",
            filetypes=[
                ("Koala files", "*.koa *.kla"),
                ("Binary files", "*.bin *.prg"),
                ("All files", "*.*"),
            ],
        )
        if not path:
            return
        try:
            with open(path, "rb") as f:
                raw = f.read()
            # Validate by attempting to strip load address and decode
            payload = strip_koala_load_address(raw)
            decode_koala_to_rgb(payload)  # will raise if malformed
        except Exception as e:
            messagebox.showerror(
                "Import failed",
                f"Couldn't read {Path(path).name} as a Koala image.\n\n{e}\n\n"
                f"Expected 10001 or 10003 bytes from tools like Multipaint or Dithertron."
            )
            return

        # Generate a scene id from the filename, deduplicating
        base = Path(path).stem.upper()
        base = "".join(c for c in base if c.isalnum() or c == "_") or "SCENE"
        sid = base
        n = 2
        existing = self.game.setdefault("scenes", {})
        while sid in existing:
            sid = f"{base}_{n}"
            n += 1

        existing[sid] = {
            "name": Path(path).stem,
            "koala_b64": base64.b64encode(payload).decode("ascii"),
            # Centre the visible band by default; the Scenes tab slider
            # adjusts it and the preview shows exactly what will ship.
            "crop_offset": CROP_CENTERED,
        }
        self.refresh_scenes_list()
        # Select the newly-added scene
        for i in range(self.scenes_listbox.size()):
            if self.scenes_listbox.get(i).split(":", 1)[0].strip() == sid:
                self.scenes_listbox.selection_clear(0, tk.END)
                self.scenes_listbox.selection_set(i)
                self.scenes_listbox.see(i)
                self.on_scene_selected(None)
                break

    def delete_scene(self):
        sid = getattr(self, "_current_scene_id", None)
        if not sid or sid not in self.game.get("scenes", {}):
            messagebox.showinfo("Delete Scene", "Please select a scene first.")
            return

        # Warn if any rooms reference it
        used_by = [rid for rid, room in self.game.get("rooms", {}).items()
                   if room.get("scene_id") == sid]
        if used_by:
            msg = (f"Scene {sid} is used by {len(used_by)} room(s):\n"
                   f"  {', '.join(used_by)}\n\n"
                   f"Deleting will clear the scene from those rooms. Continue?")
            if not messagebox.askyesno("Delete Scene", msg):
                return
        else:
            if not messagebox.askyesno("Delete Scene", f"Delete scene {sid}?"):
                return

        # Detach from any rooms that reference it
        for rid, room in self.game.get("rooms", {}).items():
            if room.get("scene_id") == sid:
                room["scene_id"] = None

        del self.game["scenes"][sid]
        self._current_scene_id = None
        self.scene_id_var.set("")
        self.scene_name_var.set("")
        self.scene_preview_label.config(image="", text="(select a scene to preview)")
        self._scene_preview_photo = None
        self.scene_usage_var.set("")
        self.refresh_scenes_list()

        # If a room is selected and just lost its scene, refresh its display
        if self._current_room_id:
            room = self.game["rooms"].get(self._current_room_id, {})
            if room.get("scene_id") is None:
                self.room_scene_id = None
                self.room_scene_display_var.set("(none)")

    def create_objects_tab(self):
        """Object editor UI"""
        left_frame = ttk.Frame(self.objects_tab)
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=False, padx=5, pady=5)
        
        ttk.Label(left_frame, text="Objects", style="Header.TLabel").pack()
        self._capacity_label(left_frame, "objects", anchor=tk.W, pady=(2, 0))
        self._capacity_label(left_frame, "carried", anchor=tk.W)

        listbox_frame = ttk.Frame(left_frame)
        listbox_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        
        scrollbar = ttk.Scrollbar(listbox_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.objects_listbox = tk.Listbox(listbox_frame, yscrollcommand=scrollbar.set,
                                         bg=self.colors["obj_list_bg"], fg=self.colors["obj_list_fg"],
                                         font=self.fonts["lg"], selectbackground=self.colors["violet_dim"], selectforeground="#ffffff",
                                         relief=tk.FLAT, bd=0, highlightthickness=0,)
        self.objects_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=self.objects_listbox.yview)
        self.objects_listbox.bind("<<ListboxSelect>>", self.on_object_selected)
        
        button_frame = ttk.Frame(left_frame)
        button_frame.pack(fill=tk.X, pady=5)
        ttk.Button(button_frame, text="+ New", command=self.add_object).pack(side=tk.LEFT, padx=2)
        ttk.Button(button_frame, text="- Delete", command=self.delete_object).pack(side=tk.LEFT, padx=2)
        
        right_frame = ttk.Frame(self.objects_tab)
        right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        ttk.Label(right_frame, text="Object Details", style="Header.TLabel").pack()
        
        id_frame = ttk.Frame(right_frame)
        id_frame.pack(fill=tk.X, pady=5)
        ttk.Label(id_frame, text="ID:").pack(side=tk.LEFT, padx=5)
        self.obj_id_var = tk.StringVar()
        tk.Entry(id_frame, textvariable=self.obj_id_var, width=10, bg=self.colors["obj_field_bg"], fg=self.colors["obj_field_fg"], insertbackground=self.colors["teal"], bd=0, relief="flat", highlightthickness=0).pack(side=tk.LEFT)
        self.obj_id_var.trace("w", self.on_object_changed)
        
        name_frame = ttk.Frame(right_frame)
        name_frame.pack(fill=tk.X, pady=5)
        ttk.Label(name_frame, text="Name:").pack(side=tk.LEFT, padx=5)
        self.obj_name_var = tk.StringVar()
        tk.Entry(name_frame, textvariable=self.obj_name_var, width=40, bg=self.colors["obj_field_bg"], fg=self.colors["obj_field_fg"], insertbackground=self.colors["teal"], bd=0, relief="flat", highlightthickness=0).pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.obj_name_var.trace("w", self.on_object_changed)
        
        room_frame = ttk.Frame(right_frame)
        room_frame.pack(fill=tk.X, pady=5)
        ttk.Label(room_frame, text="Start Room:").pack(side=tk.LEFT, padx=5)
        self.obj_room_var = tk.StringVar(value="1")
        tk.Entry(room_frame, textvariable=self.obj_room_var, width=3, bg=self.colors["obj_field_bg"], fg=self.colors["obj_field_fg"], insertbackground=self.colors["teal"], bd=0, relief="flat", highlightthickness=0).pack(side=tk.LEFT)
        self.obj_room_var.trace("w", self.on_object_changed)
        
        ttk.Label(right_frame, text="Description:").pack(anchor=tk.W, padx=5, pady=(10, 0))
        self.obj_desc_text = tk.Text(right_frame, height=4, width=50,
                                     bg=self.colors["obj_desc_bg"], fg=self.colors["obj_desc_fg"],
                                     font=self.fonts["md"], insertbackground=self.colors["violet"], wrap=tk.WORD,
                                     relief=tk.FLAT, bd=0, highlightthickness=0,)
        self.obj_desc_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.obj_desc_text.bind("<KeyRelease>", self.on_object_changed)
        
        ttk.Label(right_frame, text="Properties:").pack(anchor=tk.W, padx=5, pady=(5, 0))
        self.obj_props_var = tk.StringVar()
        tk.Entry(right_frame, textvariable=self.obj_props_var, bg=self.colors["obj_field_bg"], fg=self.colors["obj_field_fg"], insertbackground=self.colors["teal"], bd=0, relief="flat", highlightthickness=0).pack(fill=tk.X, padx=5, pady=5)
        self.obj_props_var.trace("w", self.on_object_changed)
        
        self.refresh_objects_list()
    
    def create_vocab_tab(self):
        """Vocabulary editor UI"""
        ttk.Label(self.vocab_tab, text="Vocabulary Editor", style="Header.TLabel").pack(padx=5, pady=5)
        ttk.Label(self.vocab_tab, text="Enter word=synonym,synonym format (one per line)",
                 foreground=self.colors["fg_dim"]).pack(anchor=tk.W, padx=20, pady=(0, 2))
        self._capacity_label(self.vocab_tab, "vocabulary",
                             anchor=tk.W, padx=20, pady=(0, 10))
        
        self.vocab_text = tk.Text(self.vocab_tab, height=20, width=60,
                                 bg=self.colors["bg_light"], fg=self.colors["fg_primary"],
                                 font=self.fonts["md"], insertbackground=self.colors["violet"],
                                 relief=tk.FLAT, bd=0, highlightthickness=0,)
        self.vocab_text.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)
        self.vocab_text.bind("<KeyRelease>", self.on_vocab_changed)
        
        self.refresh_vocab_display()
    
    # System message keys and their labels
    SYSTEM_MESSAGES = [
        ("CANT_GO",         "Can't Go That Way"),
        ("DONT_UNDERSTAND", "Don't Understand"),
        ("NOT_HERE",        "Object Not Here"),
        ("INVENTORY_EMPTY", "Inventory Empty"),
        ("ITEM_TAKEN",      "Item Taken"),
        ("ITEM_DROPPED",    "Item Dropped"),
        ("WIN_GAME",        "Win Game"),
    ]
    SYSTEM_DEFAULTS = {
        "CANT_GO":         "YOU CAN'T GO THAT WAY.",
        "DONT_UNDERSTAND": "I DON'T UNDERSTAND THAT.",
        "NOT_HERE":        "I DON'T SEE THAT HERE.",
        "INVENTORY_EMPTY": "YOU AREN'T CARRYING ANYTHING.",
        "ITEM_TAKEN":      "TAKEN.",
        "ITEM_DROPPED":    "DROPPED.",
        "WIN_GAME":        "CONGRATULATIONS! YOU HAVE WON!",
    }

    def create_messages_tab(self):
        """Custom messages only.

        The seven system messages that used to live here were removed: the
        text engine prints its own built-in strings and never consulted the
        table for them, and only three of the seven ever reached the
        graphical build. Win text moved to Game Settings, where it belongs as
        a single game-wide string. What remains is the part that works in
        both targets - your own named messages, referenced from a response.
        """
        frame = tk.LabelFrame(
            self.messages_tab,
            text="Custom Messages  (reference in responses with action: MSG KEYNAME)",
            bg=self.colors["bg_mid"], fg=self.colors["fg_hint"],
            font=self.fonts["sm"], bd=0, relief="flat",
            highlightthickness=0, padx=10, pady=10)
        frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        ttk.Label(frame,
                  text="Format:  KEYNAME=Your message text here  (one per line)",
                  foreground=self.colors["fg_hint"],
                  font=self.fonts["sm_bold"]).pack(anchor=tk.W, pady=(0, 2))
        ttk.Label(frame,
                  text="These work in both targets. The win message lives in "
                       "Game Settings, above.",
                  foreground=self.colors["fg_dim"],
                  font=self.fonts["sm"]).pack(anchor=tk.W, pady=(0, 2))
        self._capacity_label(frame, "messages", anchor=tk.W, pady=(0, 6))

        self.messages_text = tk.Text(
            frame, bg=self.colors["custmsg_bg"], fg=self.colors["custmsg_fg"],
            font=self.fonts["md"], insertbackground=self.colors["violet"],
            wrap=tk.WORD, relief=tk.FLAT, bd=0, highlightthickness=0)
        self.messages_text.pack(fill=tk.BOTH, expand=True)
        self.messages_text.bind("<KeyRelease>", lambda e: self.on_messages_changed())

        self.refresh_messages_display()

    @staticmethod
    def _int_field(text, fallback):
        """Read a number out of a live entry without raising.

        These fields are traced on every keystroke, so they are read
        mid-edit: empty while the user clears them, and briefly holding a
        stray letter. Anything unparseable keeps the last good value rather
        than crashing the callback and leaving the widget half-updated.
        """
        text = (text or "").strip()
        if text == "":
            return fallback
        try:
            return int(text)
        except (TypeError, ValueError):
            return fallback

    def _capacity_label(self, parent, key, **pack):
        """A live counter for one of the text runtime's fixed limits."""
        var = tk.StringVar(value="")
        lbl = tk.Label(parent, textvariable=var,
                       bg=self.colors["bg_dark"], fg=self.colors["fg_hint"],
                       font=self.fonts["sm"], anchor=tk.W, justify=tk.LEFT)
        lbl.pack(**pack)
        if not hasattr(self, "_capacity_vars"):
            self._capacity_vars = {}
        self._capacity_vars[key] = var
        return lbl

    def adopt_undefined_nouns(self):
        """Turn an undeclared noun into a real, hidden object.

        A response like TALK WIZARD names something with no object behind it.
        The build used to invent a stand-in that the author never saw. It is
        added to the Objects list instead, marked HIDDEN so it is never
        listed in the room - the secret survives, and the author can now give
        it a description.

        Only nouns with an AT condition are adopted, since that is the only
        way to know which room they belong in. Returns the ids added.
        """
        objects = self.game.setdefault("objects", {})
        added = []
        for resp in self.game.get("responses", []):
            for word in undefined_nouns(resp, self.game):
                room = None
                for term in (resp.get("condition") or "").upper().split(","):
                    term = term.strip()
                    if term.startswith("AT "):
                        room = term[3:].strip()
                        break
                if not room or not room.isdigit():
                    continue
                if word in objects:
                    continue
                objects[word] = {
                    "name": word,
                    "start_room": int(room),
                    "description": "",
                    "properties": "HIDDEN",
                }
                added.append(word)
        return added

    def refresh_capacity(self):
        """Update every counter from the current game."""
        if not hasattr(self, "_capacity_vars"):
            return
        counts = basic_capacity(self.game)
        for key, var in self._capacity_vars.items():
            count, limit = counts[key]
            var.set(capacity_text(key, count, limit))

    RESP_GUTTER_W = 15          # characters; fits "graphics only"

    def create_responses_tab(self):
        """Responses editor, with a per-row note of what the text engine does.

        The two targets diverge most here: a verb the BASIC runtime has never
        heard of, or an action it cannot perform, silently becomes nothing.
        The gutter says which rows survive that, while you are writing them.
        """
        ttk.Label(self.responses_tab, text="Responses Editor",
                  style="Header.TLabel").pack(padx=5, pady=5)
        ttk.Label(self.responses_tab,
                  text="Format: COMMAND:CONDITION:MESSAGE:ACTION (one per line)",
                  foreground=self.colors["fg_dim"]).pack(anchor=tk.W, padx=20, pady=(0, 2))
        ttk.Label(self.responses_tab,
                  text="The left column says whether each row runs in BOTH targets "
                       "or only in the graphical build.",
                  foreground=self.colors["fg_dim"]).pack(anchor=tk.W, padx=20, pady=(0, 2))
        self._capacity_label(self.responses_tab, "responses", anchor=tk.W, padx=20)
        self._capacity_label(self.responses_tab, "flags", anchor=tk.W, padx=20,
                             pady=(0, 8))

        editor = ttk.Frame(self.responses_tab)
        editor.pack(fill=tk.BOTH, expand=True, padx=20, pady=(0, 6))

        self.responses_gutter = tk.Text(
            editor, width=self.RESP_GUTTER_W, height=18,
            bg=self.colors["bg_mid"], fg=self.colors["fg_hint"],
            font=self.fonts["base"], relief=tk.FLAT, bd=0,
            highlightthickness=0, padx=6, wrap=tk.NONE, takefocus=0,
            cursor="arrow", state=tk.DISABLED,
        )
        self.responses_gutter.pack(side=tk.LEFT, fill=tk.Y)

        scroll = ttk.Scrollbar(editor, command=self._responses_yview)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.responses_scroll = scroll

        self.responses_text = tk.Text(
            editor, height=18, width=80,
            bg=self.colors["responses_bg"], fg=self.colors["responses_fg"],
            font=self.fonts["base"], insertbackground=self.colors["teal"],
            relief=tk.FLAT, bd=0, highlightthickness=0,
            yscrollcommand=self._responses_scrolled,
        )
        self.responses_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.responses_text.bind("<KeyRelease>", self.on_responses_changed)

        detail = tk.LabelFrame(
            self.responses_tab,
            text="What the text engine does differently",
            bg=self.colors["bg_mid"], fg=self.colors["fg_hint"],
            font=self.fonts["sm"], bd=0, relief="flat",
            highlightthickness=0, padx=10, pady=6,
        )
        detail.pack(fill=tk.X, padx=20, pady=(0, 10))

        detail_scroll = ttk.Scrollbar(detail)
        detail_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        self.responses_detail = tk.Text(
            detail, height=6, bg=self.colors["bg_dark"],
            fg=self.colors["fg_primary"], font=self.fonts["sm"],
            relief=tk.FLAT, bd=0, highlightthickness=0, wrap=tk.WORD,
            state=tk.DISABLED, yscrollcommand=detail_scroll.set,
        )
        self.responses_detail.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        detail_scroll.config(command=self.responses_detail.yview)
        self.responses_detail_scroll = detail_scroll

        self.refresh_responses_display()

    # -- scroll the gutter in step with the editor -----------------------
    def _responses_yview(self, *args):
        self.responses_text.yview(*args)
        self.responses_gutter.yview(*args)

    def _responses_scrolled(self, first, last):
        self.responses_scroll.set(first, last)
        self.responses_gutter.yview_moveto(first)

    def refresh_responses_compat(self):
        """Recompute the gutter and the detail panel from the editor text."""
        if not hasattr(self, "responses_gutter"):
            return
        raw = self.responses_text.get(1.0, tk.END).rstrip("\n")
        marks, details = [], []
        for n, line in enumerate(raw.split("\n"), 1):
            if not line.strip():
                marks.append("")
                continue
            if ":" not in line:
                marks.append("not a response")
                details.append(f"Line {n}: not in COMMAND:CONDITION:MESSAGE:ACTION form.")
                continue
            parts = line.split(":")
            resp = {
                "command":   parts[0].strip(),
                "condition": parts[1].strip() if len(parts) > 1 else "",
                "message":   parts[2].strip() if len(parts) > 2 else "",
                "action":    parts[3].strip() if len(parts) > 3 else "",
            }
            problems = basic_incompatibilities(resp)
            marks.append("both" if not problems else "graphics only")
            for p in problems:
                details.append(f"Line {n}: {p}")
            for word in undefined_nouns(resp, self.game):
                details.append(f"Line {n}: {undefined_noun_note(word, resp)}")

        self.responses_gutter.config(state=tk.NORMAL)
        self.responses_gutter.delete(1.0, tk.END)
        self.responses_gutter.insert(1.0, "\n".join(marks))
        self.responses_gutter.config(state=tk.DISABLED)
        self.responses_gutter.yview_moveto(self.responses_text.yview()[0])

        total = sum(1 for m in marks if m)
        both = sum(1 for m in marks if m == "both")
        if details:
            head = f"{both} of {total} responses run in both targets.\n\n"
            body = head + "\n".join(details)
        elif total:
            body = f"All {total} responses run in both targets, with nothing to flag."
        else:
            body = "No responses yet."
        self.responses_detail.config(state=tk.NORMAL)
        self.responses_detail.delete(1.0, tk.END)
        self.responses_detail.insert(1.0, body)
        self.responses_detail.config(state=tk.DISABLED)
        self.responses_detail.yview_moveto(0)
    
    def create_player_tab(self):
        """Game player UI"""
        tk.Label(self.player_tab,
                 text="Text only. This plays your game's logic - rooms, "
                      "objects, conditions and responses - and matches what "
                      "the .adv build does. It never shows room artwork; to "
                      "see your scenes, build the C64 disk.",
                 bg=self.colors["bg_dark"], fg=self.colors["fg_hint"],
                 font=self.fonts["sm"], anchor=tk.W, justify=tk.LEFT,
                 wraplength=900).pack(anchor=tk.W, padx=10, pady=(10, 0))

        # Control buttons
        control_frame = ttk.Frame(self.player_tab)
        control_frame.pack(fill=tk.X, padx=10, pady=10)
        
        ttk.Button(control_frame, text="▶ Start Game", command=self.start_game).pack(side=tk.LEFT, padx=5)
        ttk.Button(control_frame, text="↻ Restart", command=self.restart_game).pack(side=tk.LEFT, padx=5)
        ttk.Button(control_frame, text="📋 Debug", command=self.toggle_debug).pack(side=tk.LEFT, padx=5)
        
        # Main split
        main_frame = ttk.Frame(self.player_tab)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        # Game display (left/top)
        game_frame = ttk.Frame(main_frame)
        game_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 5))
        
        ttk.Label(game_frame, text="Game Output", style="Header.TLabel").pack()

        # Input area — packed FIRST with side=BOTTOM so it always keeps its
        # own reserved space at the bottom of game_frame, no matter how
        # tall the scene image or output text end up being. Previously this
        # was packed last with no side, so a large scene image could push
        # it out of the visible window entirely with no way to reach it.
        input_frame = ttk.Frame(game_frame)
        input_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=5)

        ttk.Label(input_frame, text="Command:").pack(side=tk.LEFT)
        self.game_input = tk.Entry(input_frame, bg=self.colors["game_input_bg"], fg=self.colors["game_input_fg"], insertbackground=self.colors["teal"], bd=0, relief="flat", highlightthickness=0)
        self.game_input.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        self.game_input.bind("<Return>", lambda e: self.execute_game_command())

        ttk.Button(input_frame, text="Go", command=self.execute_game_command).pack(side=tk.LEFT)

        # Game output text — fills whatever space remains between the
        # header above and the input bar reserved below.
        self.game_output = tk.Text(game_frame, height=20, width=60,
                                  bg=self.colors["game_output_bg"], fg=self.colors["game_output_fg"],
                                  font=self.fonts["base"], wrap=tk.WORD, state=tk.DISABLED,
                                  relief=tk.FLAT, bd=0, highlightthickness=0,)
        self.game_output.pack(fill=tk.BOTH, expand=True, pady=5)
        
        # State panel (right)
        state_frame = tk.LabelFrame(main_frame, text="Game State", padx=5, pady=5, bg=self.colors["bg_mid"], fg=self.colors["fg_hint"], font=self.fonts["sm"], bd=0, relief="flat", highlightthickness=0)
        state_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=False, padx=5)
        
        # Score
        tk.Label(state_frame, text="Score:", font=self.fonts["base_bold"],
                 bg=self.colors["bg_mid"], fg=self.colors["accent"]).pack(anchor=tk.W)
        self.score_var = tk.StringVar(value="0 / 100")
        tk.Label(state_frame, textvariable=self.score_var, font=self.fonts["base"],
                 bg=self.colors["bg_mid"], fg=self.colors["orange"]).pack(anchor=tk.W, padx=10, pady=(0, 5))
        
        # Inventory
        tk.Label(state_frame, text="Inventory:", font=self.fonts["base_bold"],
                 bg=self.colors["bg_mid"], fg=self.colors["accent"]).pack(anchor=tk.W, pady=(10, 0))
        self.inventory_text = tk.Text(state_frame, height=4, width=30,
                                     bg=self.colors["inventory_bg"], fg=self.colors["inventory_fg"],
                                     font=self.fonts["sm"], insertbackground=self.colors["violet"],
                                     relief=tk.FLAT, bd=0, highlightthickness=0,)
        self.inventory_text.pack(fill=tk.BOTH, expand=False, padx=5, pady=5)
        
        # Current room
        tk.Label(state_frame, text="Current Room:", font=self.fonts["base_bold"],
                 bg=self.colors["bg_mid"], fg=self.colors["accent"]).pack(anchor=tk.W, pady=(10, 0))
        self.room_var = tk.StringVar(value="1")
        tk.Label(state_frame, textvariable=self.room_var, font=self.fonts["base"],
                 bg=self.colors["bg_mid"], fg=self.colors["sage"]).pack(anchor=tk.W, padx=10, pady=(0, 5))
        
        # Debug log
        tk.Label(state_frame, text="Debug Log:", font=self.fonts["base_bold"],
                 bg=self.colors["bg_mid"], fg=self.colors["accent"]).pack(anchor=tk.W, pady=(10, 0))
        self.debug_text = tk.Text(state_frame, height=10, width=30,
                                 bg=self.colors["debug_bg"], fg=self.colors["debug_fg"],
                                 font=self.fonts["xs"], relief=tk.FLAT, bd=0, highlightthickness=0,)
        self.debug_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        self.debug_visible = False
    
    def start_game(self):
        """Start a new game"""
        # Force sync all data from text fields
        self.on_vocab_changed()
        self.on_messages_changed()
        self.on_responses_changed()
        
        self.game_engine = GameEngine(self.game)
        self.update_game_display()
        self.game_input.focus()
    
    def restart_game(self):
        """Restart the current game"""
        if self.game_engine:
            # Force sync all data from text fields
            self.on_vocab_changed()
            self.on_messages_changed()
            self.on_responses_changed()
            
            self.game_engine = GameEngine(self.game)
            self.update_game_display()
            self.game_input.focus()
    
    def toggle_debug(self):
        """Toggle debug panel visibility"""
        self.debug_visible = not self.debug_visible
        if self.debug_visible and self.game_engine:
            self.update_debug_display()
    
    def execute_game_command(self):
        """Execute player command in game"""
        if not self.game_engine:
            self.start_game()
            return

        cmd = self.game_input.get().strip()
        if not cmd:
            return

        message, actions = self.game_engine.execute_command(cmd)

        # Append command and response to output — never wipe it
        self.game_output.config(state=tk.NORMAL)
        self.game_output.insert(tk.END, f"\n> {cmd}\n{message}\n")
        if actions:
            for action_msg in actions:
                self.game_output.insert(tk.END, f"{action_msg}\n")
        self.game_output.see(tk.END)
        self.game_output.config(state=tk.DISABLED)

        self.game_input.delete(0, tk.END)
        self.update_state_panel()

    def update_game_display(self):
        """Show initial room description when game starts"""
        if not self.game_engine:
            return

        # Clear output and show opening room description
        self.game_output.config(state=tk.NORMAL)
        self.game_output.delete(1.0, tk.END)
        title = self.game_engine.game["settings"].get("title", "Adventure")
        self.game_output.insert(tk.END, f"{title}\n{'='*40}\n")
        self.game_output.insert(tk.END, self.game_engine.room_description())
        self.game_output.config(state=tk.DISABLED)

        self.update_state_panel()

    def update_state_panel(self):
        """Update score, inventory, room — never touch game output"""
        if not self.game_engine:
            return

        self.score_var.set(f"{self.game_engine.score} / {self.game_engine.max_score}")
        self.room_var.set(f"Room {self.game_engine.current_room}")

        self.inventory_text.config(state=tk.NORMAL)
        self.inventory_text.delete(1.0, tk.END)
        inv = self.game_engine.inventory_objects()
        if inv:
            names = chr(10).join(od["name"] for _, od in inv)
            self.inventory_text.insert(1.0, names)
        else:
            self.inventory_text.insert(1.0, "(empty)")
        self.inventory_text.config(state=tk.DISABLED)

        if self.debug_visible:
            self.update_debug_display()
    
    def update_debug_display(self):
        """Update debug log"""
        self.debug_text.config(state=tk.NORMAL)
        self.debug_text.delete(1.0, tk.END)
        for line in self.game_engine.debug_log[-20:]:
            self.debug_text.insert(tk.END, line + "\n")
        self.debug_text.see(tk.END)
        self.debug_text.config(state=tk.DISABLED)
    
    # Event handlers (rooms)
    def update_setting(self, key, value):
        self.game["settings"][key] = value

    def on_room_selected(self, event):
        selection = self.rooms_listbox.curselection()
        if not selection:
            return

        room_id_str = self.rooms_listbox.get(selection[0]).split(":")[0].strip()
        if room_id_str not in self.game["rooms"]:
            return

        self._current_room_id = room_id_str  # track for delete

        room = self.game["rooms"][room_id_str]
        self._suppress_room_changes = True
        self.room_id_var.set(room_id_str)
        self.room_name_var.set(room.get("name", ""))
        self.room_desc_text.delete(1.0, tk.END)
        self.room_desc_text.insert(1.0, room.get("description", ""))
        self.room_exit_n.set(str(room.get("exits", [0, 0, 0, 0])[0]))
        self.room_exit_s.set(str(room.get("exits", [0, 0, 0, 0])[1]))
        self.room_exit_e.set(str(room.get("exits", [0, 0, 0, 0])[2]))
        self.room_exit_w.set(str(room.get("exits", [0, 0, 0, 0])[3]))

        # Scene selection — read whichever key the room stores it under.
        # scene_id may be missing entirely on legacy rooms; treat as None.
        sid = room.get("scene_id")
        self.room_scene_id = sid if sid and sid in self.game.get("scenes", {}) else None
        if self.room_scene_id is None:
            self.room_scene_display_var.set("(none)")
        else:
            name = self.game["scenes"][self.room_scene_id].get("name", "")
            self.room_scene_display_var.set(
                f"{self.room_scene_id}   {name}" if name else self.room_scene_id
            )
        self._suppress_room_changes = False
    
    def on_room_changed(self, *args):
        if getattr(self, "_suppress_room_changes", False):
            return
        room_id_str = self.room_id_var.get().strip()
        if not room_id_str or room_id_str == "0":
            return
        
        # Keep whatever the room already had for any exit that is mid-edit,
        # so a stray keystroke never silently clears a connection.
        prev = self.game["rooms"].get(room_id_str, {}).get("exits", [0, 0, 0, 0])
        prev = (list(prev) + [0, 0, 0, 0])[:4]
        self.game["rooms"][room_id_str] = {
            "name": self.room_name_var.get(),
            "description": self.room_desc_text.get(1.0, tk.END).strip(),
            "exits": [
                self._int_field(self.room_exit_n.get(), prev[0]),
                self._int_field(self.room_exit_s.get(), prev[1]),
                self._int_field(self.room_exit_e.get(), prev[2]),
                self._int_field(self.room_exit_w.get(), prev[3]),
            ],
            "scene_id": getattr(self, "room_scene_id", None),
        }
        self.refresh_rooms_list()
    
    def add_room(self):
        if self.game["rooms"]:
            numeric_ids = []
            for key in self.game["rooms"].keys():
                try:
                    numeric_ids.append(int(key))
                except (ValueError, TypeError):
                    pass
            new_id = max(numeric_ids) + 1 if numeric_ids else 1
        else:
            new_id = 1
        
        new_id_str = str(new_id)
        self.game["rooms"][new_id_str] = {
            "name": f"Room {new_id}",
            "description": "",
            "exits": [0, 0, 0, 0],
            "scene_id": None,
        }
        self.refresh_rooms_list()
    
    def delete_room(self):
        room_id_str = getattr(self, "_current_room_id", None)
        if not room_id_str or room_id_str not in self.game["rooms"]:
            messagebox.showinfo("Delete Room", "Please select a room first.")
            return

        if not messagebox.askyesno("Delete Room", f"Delete room {room_id_str}?"):
            return

        self.game["rooms"].pop(room_id_str, None)
        self.map_positions.pop(room_id_str, None)
        if self._selected_map_room == room_id_str:
            self._selected_map_room = None
        self._current_room_id = None

        self._suppress_room_changes = True
        self.room_id_var.set("")
        self.room_name_var.set("")
        self.room_desc_text.delete(1.0, tk.END)
        self.room_exit_n.set("0")
        self.room_exit_s.set("0")
        self.room_exit_e.set("0")
        self.room_exit_w.set("0")
        self.room_scene_id = None
        self.room_scene_display_var.set("(none)")
        self._suppress_room_changes = False

        self.refresh_rooms_list()
    
    def refresh_rooms_list(self):
        self.refresh_capacity()
        self.rooms_listbox.delete(0, tk.END)
        room_ids = []
        for key in self.game["rooms"].keys():
            try:
                room_ids.append((int(key), key))
            except (ValueError, TypeError):
                room_ids.append((999, key))
        room_ids.sort()

        for _, room_id in room_ids:
            name = self.game["rooms"][room_id]["name"]
            self.rooms_listbox.insert(tk.END, f"{room_id}: {name}")

        # Keep map in sync
        if hasattr(self, "map_canvas"):
            self.refresh_map()
    
    # Event handlers (objects)
    def on_object_selected(self, event):
        selection = self.objects_listbox.curselection()
        if not selection:
            return
        
        obj_id = self.objects_listbox.get(selection[0]).split(":")[0]
        if obj_id not in self.game["objects"]:
            return
        
        obj = self.game["objects"][obj_id]
        self.obj_id_var.set(obj_id)
        self.obj_name_var.set(obj.get("name", ""))
        self.obj_room_var.set(str(obj.get("start_room", 1)))
        self.obj_desc_text.delete(1.0, tk.END)
        self.obj_desc_text.insert(1.0, obj.get("description", ""))
        self.obj_props_var.set(obj.get("properties", ""))
    
    def on_object_changed(self, *args):
        obj_id = self.obj_id_var.get()
        if not obj_id:
            return
        
        self.game["objects"][obj_id] = {
            "name": self.obj_name_var.get(),
            "start_room": self._int_field(
                self.obj_room_var.get(),
                self.game["objects"].get(obj_id, {}).get("start_room", 1)),
            "description": self.obj_desc_text.get(1.0, tk.END).strip(),
            "properties": self.obj_props_var.get()
        }
        self.refresh_objects_list()
    
    def add_object(self):
        obj_id = f"OBJ{len(self.game['objects']) + 1}"
        self.game["objects"][obj_id] = {
            "name": f"Object {obj_id}",
            "start_room": 1,
            "description": "",
            "properties": ""
        }
        self.refresh_objects_list()
    
    def delete_object(self):
        selection = self.objects_listbox.curselection()
        if not selection:
            return
        
        obj_id = self.objects_listbox.get(selection[0]).split(":")[0]
        if messagebox.askyesno("Delete Object", f"Delete {obj_id}?"):
            del self.game["objects"][obj_id]
            self.refresh_objects_list()
    
    def refresh_objects_list(self):
        self.refresh_capacity()
        self.objects_listbox.delete(0, tk.END)
        for obj_id in sorted(self.game["objects"].keys()):
            name = self.game["objects"][obj_id]["name"]
            self.objects_listbox.insert(tk.END, f"{obj_id}: {name}")
    
    # Event handlers (vocab, messages, responses)
    def on_vocab_changed(self, *args):
        text = self.vocab_text.get(1.0, tk.END).strip()
        self.game["vocabulary"] = {}
        for line in text.split("\n"):
            if "=" in line:
                parts = line.split("=")
                if len(parts) == 2:
                    word = parts[0].strip()
                    synonyms = [s.strip() for s in parts[1].split(",")]
                    self.game["vocabulary"][word] = synonyms
    
    def refresh_vocab_display(self):
        self.refresh_capacity()
        self.vocab_text.delete(1.0, tk.END)
        for word, synonyms in self.game["vocabulary"].items():
            self.vocab_text.insert(tk.END, f"{word}={','.join(synonyms)}\n")
    
    def on_messages_changed(self, *args):
        """Read the custom message table back out of the text area."""
        msgs = {}
        text = self.messages_text.get(1.0, tk.END).strip()
        for line in text.split("\n"):
            if "=" in line:
                parts = line.split("=", 1)
                key = parts[0].strip().upper()
                val = parts[1].strip()
                if key and val:
                    msgs[key] = val

        self.game["messages"] = msgs
        self.refresh_capacity()

    def refresh_messages_display(self):
        """Show the custom message table."""
        msgs = self.game.get("messages", {})
        lines = [f"{key}={val}" for key, val in msgs.items()]
        if hasattr(self, "messages_text"):
            self.messages_text.delete(1.0, tk.END)
            self.messages_text.insert(1.0, "\n".join(lines))
    
    def on_responses_changed(self, *args):
        text = self.responses_text.get(1.0, tk.END).strip()
        self.game["responses"] = []
        for line in text.split("\n"):
            if line.strip() and ":" in line:
                parts = line.split(":")
                if len(parts) >= 3:
                    self.game["responses"].append({
                        "command": parts[0].strip(),
                        "condition": parts[1].strip() if len(parts) > 1 else "",
                        "message": parts[2].strip() if len(parts) > 2 else "",
                        "action": parts[3].strip() if len(parts) > 3 else ""
                    })
        self.refresh_responses_compat()
        self.refresh_capacity()
    
    def refresh_responses_display(self):
        self.responses_text.delete(1.0, tk.END)
        for resp in self.game["responses"]:
            line = f"{resp['command']}:{resp['condition']}:{resp['message']}:{resp['action']}\n"
            self.responses_text.insert(tk.END, line)
        self.refresh_responses_compat()
    
    # File operations
    def new_game(self):
        self.game = {
            "settings": {"title": "New Adventure", "author": "", "version": "1.0", "startroom": 1, "maxscore": 100},
            "rooms": {"1": {"name": "Start", "description": "You are here.", "exits": [0, 0, 0, 0], "scene_id": None}},
            "objects": {},
            "vocabulary": {"NORTH": ["N"], "SOUTH": ["S"], "EAST": ["E"], "WEST": ["W"]},
            "messages": {},
            "responses": [],
            "scenes": {},
        }
        self.current_file = None
        self.refresh_all()
    
    def open_game(self):
        self.root.after(100, self._do_open_game)

    def _do_open_game(self):
        path = filedialog.askopenfilename(filetypes=[("JSON files", "*.json"), ("All files", "*.*")])
        if not path:
            return

        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # Ensure all required top-level keys exist
            data.setdefault("settings",   {"title": "", "author": "", "version": "1.0", "startroom": 1, "maxscore": 100})
            data.setdefault("rooms",      {})
            data.setdefault("objects",    {})
            data.setdefault("vocabulary", {})
            data.setdefault("messages",   {})
            data.setdefault("responses",  [])
            data.setdefault("scenes",     {})

            # Normalise responses — must be a list of dicts
            if isinstance(data["responses"], list):
                fixed = []
                for r in data["responses"]:
                    if isinstance(r, dict):
                        r.setdefault("command",   "")
                        r.setdefault("condition", "")
                        r.setdefault("message",   "")
                        r.setdefault("action",    "")
                        fixed.append(r)
                data["responses"] = fixed

            # Normalise vocabulary — must be a dict of str→list
            if isinstance(data["vocabulary"], dict):
                for k, v in data["vocabulary"].items():
                    if isinstance(v, str):
                        data["vocabulary"][k] = [v]

            # Normalise rooms — ensure scene_id key exists on every room, and
            # drop scene_ids that reference scenes that don't exist (stale data).
            valid_scene_ids = set(data["scenes"].keys()) if isinstance(data["scenes"], dict) else set()
            if isinstance(data["rooms"], dict):
                for rid, room in data["rooms"].items():
                    if not isinstance(room, dict):
                        continue
                    sid = room.get("scene_id")
                    if sid and sid not in valid_scene_ids:
                        room["scene_id"] = None
                    else:
                        room.setdefault("scene_id", None)

            # Normalise scenes — each entry should have name + koala_b64
            if isinstance(data["scenes"], dict):
                for sid, sd in list(data["scenes"].items()):
                    if not isinstance(sd, dict):
                        del data["scenes"][sid]
                        continue
                    sd.setdefault("name", sid)
                    sd.setdefault("koala_b64", "")

            self.game = data
            self.current_file = path
            self.refresh_all()

        except Exception as e:
            messagebox.showerror("Error", f"Failed to open file:\n{e}")
    
    def save_game(self):
        if not self.current_file:
            self.save_game_as()
            return
        
        try:
            with open(self.current_file, 'w') as f:
                json.dump(self.game, f, indent=2)
            messagebox.showinfo("Success", "Game saved!")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save: {e}")
    
    def save_game_as(self):
        self.root.after(100, self._do_save_game_as)

    def _do_save_game_as(self):
        path = filedialog.asksaveasfilename(defaultextension=".json", 
                                           filetypes=[("JSON files", "*.json"), ("All files", "*.*")])
        if path:
            self.current_file = path
            self.save_game()
    
    def export_adv(self):
        self.root.after(100, self._do_export_adv)


    # ------------------------------------------------------------------
    # StoryTllr export — graphical game for the StoryTllrC64 engine
    # ------------------------------------------------------------------


    # ------------------------------------------------------------------
    # One-click C64 build: convert -> compile -> .d64 -> (emulator)
    # ------------------------------------------------------------------

    KIT_CONFIG_NAME = "c64kit_config.json"

    def _kit_dir(self):
        return Path(__file__).resolve().parent

    BASIC_RUNTIME = "advplay-c64-current.bas"

    def _kit_basic_runtime(self):
        """The BASIC player source shipped in legacy/."""
        path = self._kit_dir() / "legacy" / self.BASIC_RUNTIME
        return path if path.exists() else None

    def _kit_engine_file(self, name):
        """Find a bundled engine file (engine/ next to the editor)."""
        p = self._kit_dir() / "engine" / name
        return p if p.exists() else None

    def _load_kit_config(self):
        try:
            with open(self._kit_dir() / self.KIT_CONFIG_NAME, "r") as f:
                return json.load(f)
        except Exception:
            return {}

    def _save_kit_config(self, cfg):
        try:
            with open(self._kit_dir() / self.KIT_CONFIG_NAME, "w") as f:
                json.dump(cfg, f, indent=2)
        except Exception:
            pass  # config is a convenience; never block on it

    def _find_tool(self, cfg_key, names, extra_dirs):
        """Locate a tool: saved config, then PATH, then common locations.

        `extra_dirs` entries may contain `~` and glob wildcards (VICE ships
        under version-stamped directory names on macOS and Windows).
        """
        cfg = self._load_kit_config()
        saved = cfg.get(cfg_key)
        if saved and Path(saved).exists():
            return saved
        for n in names:
            found = shutil.which(n)
            if found:
                return found
        home = Path.home()
        for d in extra_dirs:
            pattern = str(d).replace("~", str(home))
            roots = sorted(glob.glob(pattern)) if any(
                c in pattern for c in "*?[") else [pattern]
            for root in roots:
                for n in names:
                    p = Path(root) / n
                    if p.exists():
                        return str(p)
        return None

    def _find_script_compiler(self):
        return self._find_tool(
            "script_compiler", self._exe_names("script_compiler"),
            [self._kit_dir(), self._kit_dir() / "tools",
             "~/dev/storytllr-mac-port"])

    def _find_petcat(self):
        """petcat tokenises the BASIC runtime; it ships with VICE."""
        return self._find_tool("petcat", self._exe_names("petcat"), VICE_DIRS)

    def _find_c1541(self):
        return self._find_tool(
            "c1541", self._exe_names("c1541"), VICE_DIRS)

    def _find_x64sc(self):
        return self._find_tool(
            "x64sc", self._exe_names("x64sc"), VICE_DIRS)

    @staticmethod
    def _exe_names(stem):
        """Executable file names to try for `stem` on this platform."""
        return [stem + ".exe", stem] if os.name == "nt" else [stem]

    def export_and_build(self):
        """File > Export & Build C64 Disk... — entry point."""
        self.root.after(100, self._do_export_and_build)

    def _do_export_and_build(self):
        # 1. Analyse (writes nothing yet) and show plain-language notes.
        try:
            conv = Converter(self.game, crop_offset=STORYTLLR_CROP_OFFSET)
        except Exception as e:
            messagebox.showerror("Build failed", f"Could not analyse game: {e}")
            return
        no_scene = [rid for rid, room in self.game.get("rooms", {}).items()
                    if not room.get("scene_id")]
        advisories = list(dict.fromkeys(conv.warnings))
        if no_scene:
            advisories.append(
                f"{len(no_scene)} room(s) have no scene attached — a simple "
                f"colored placeholder image will be used for them.")
        advisories += list(dict.fromkeys(conv.notes))
        if advisories:
            msg = "Before building, a few notes:\n\n"
            msg += "\n".join(f"• {w}" for w in advisories)
            msg += "\n\nBuild anyway?"
            if not messagebox.askyesno("Build C64 disk", msg):
                return

        # 2. Locate tools (ask for the compiler if we can't find it).
        compiler = self._find_script_compiler()
        if not compiler:
            messagebox.showinfo(
                "Locate compiler",
                "I couldn't find the StoryTllr compiler (script_compiler).\n"
                "Please locate it in the next dialog — it only needs doing "
                "once.")
            compiler = filedialog.askopenfilename(title="Locate script_compiler")
            if not compiler:
                return
            cfg = self._load_kit_config()
            cfg["script_compiler"] = compiler
            self._save_kit_config(cfg)
        c1541 = self._find_c1541()
        if not c1541:
            messagebox.showerror(
                "VICE not found",
                "I couldn't find c1541 (part of the VICE emulator), which "
                "is needed to build the disk image. Install VICE or use "
                "File > Export StoryTllr Project for a manual build.")
            return

        # 3. Pick where builds live (remembered between sessions).
        cfg = self._load_kit_config()
        build_root = cfg.get("build_dir")
        if not build_root or not Path(build_root).exists():
            build_root = filedialog.askdirectory(
                title="Choose a folder to keep your C64 builds in")
            if not build_root:
                return
            cfg["build_dir"] = build_root
            self._save_kit_config(cfg)

        self.root.after(50, lambda: self._run_build(conv, compiler, c1541,
                                                    Path(build_root)))

    def _run_build(self, conv, compiler, c1541, build_root):
        import subprocess
        try:
            slug = slugify(self.game.get("settings", {}).get("title", "game"))
            proj = build_root / slug
            proj.mkdir(parents=True, exist_ok=True)
            (proj / "img").mkdir(exist_ok=True)

            # Self-contained project: font travels with it.
            font_src = self._kit_engine_file("font.png")
            if font_src:
                (proj / "png").mkdir(exist_ok=True)
                shutil.copy(font_src, proj / "png" / "font.png")
                font_ref = "png\\font.png"
            else:
                font_ref = "..\\shared\\png\\font.png"  # engine-repo layout

            script = conv.emit(font_path=font_ref)
            (proj / f"{slug}.hjt").write_text(script, encoding="utf-8")
            conv.write_room_images(proj / "png")

            stdlib_src = self._kit_engine_file("stdlib.hjt")
            if not stdlib_src:
                # fall back to searching around the build folder
                probe = build_root.resolve()
                for _ in range(5):
                    for cand in (probe / "samples" / "accuse" / "stdlib.hjt",
                                 probe / "accuse" / "stdlib.hjt",
                                 probe / "shared" / "stdlib.hjt"):
                        if cand.exists():
                            stdlib_src = cand
                            break
                    if stdlib_src:
                        break
                    probe = probe.parent
            if not stdlib_src:
                messagebox.showerror(
                    "Missing stdlib.hjt",
                    "The engine library stdlib.hjt wasn't found. Keep the "
                    "editor inside its kit folder (with the engine/ folder "
                    "next to it), or copy stdlib.hjt next to the editor.")
                return
            shutil.copy(stdlib_src, proj / "stdlib.hjt")

            # Compile. (Note: this compiler's exit code is 1 on SUCCESS,
            # so we judge by ERR lines and output files instead.)
            r = subprocess.run([compiler, f"{slug}.hjt", "tmp.h", "advcartridge"],
                               cwd=proj, capture_output=True, text=True)
            output = (r.stdout or "") + (r.stderr or "")
            err_lines = [l for l in output.splitlines() if l.startswith("ERR")]
            if err_lines or not (proj / "advcartridge").exists():
                messagebox.showerror(
                    "Compile failed",
                    "The game didn't compile:\n\n" + "\n".join(err_lines[:12]))
                return

            # Build the .d64.
            player = self._kit_engine_file("storytllr64.prg")
            if not player:
                messagebox.showerror(
                    "Missing player",
                    "storytllr64.prg wasn't found in the kit's engine/ "
                    "folder — the disk can't be built without it.")
                return
            disk = proj / "bin" / f"{slug}.d64"
            disk.parent.mkdir(exist_ok=True)
            if disk.exists():
                disk.unlink()
            label = slug[:16]

            def run1541(*args):
                rr = subprocess.run([c1541, *args], capture_output=True, text=True)
                return rr.returncode, (rr.stdout or "") + (rr.stderr or "")

            rc, out = run1541("-format", f"{label},66", "d64", str(disk))
            if not disk.exists():
                messagebox.showerror("Disk build failed",
                                     f"Could not create the disk image:\n{out}")
                return
            writes = [(str(player), label)]
            writes.append((str(proj / "img" / "font"), "font"))
            writes.append((str(proj / "advcartridge"), "advcartridge"))
            for f in sorted((proj / "img").glob("room*")):
                writes.append((str(f), f.name))
            for src, dst in writes:
                rc, out = run1541("-attach", str(disk), "-write", src, dst.lower())
                if rc != 0:
                    messagebox.showerror(
                        "Disk build failed",
                        f"Could not write {dst} to the disk:\n{out}")
                    return

            # Done — offer to play.
            x64sc = self._find_x64sc()
            msg = (f"Your C64 game is ready!\n\nDisk image:\n{disk}\n\n"
                   f"Load it in any C64 emulator, or write it to real "
                   f"hardware.")
            if x64sc:
                if messagebox.askyesno("Build complete",
                                       msg + "\n\nPlay it now in VICE?"):
                    subprocess.Popen([x64sc, str(disk)],
                                     stdout=subprocess.DEVNULL,
                                     stderr=subprocess.DEVNULL)
            else:
                messagebox.showinfo("Build complete", msg)
        except Exception as e:
            messagebox.showerror("Build failed", f"Unexpected error: {e}")

    def export_and_build_text(self):
        """File > Export & Build C64 Disk (text only) — entry point."""
        self.root.after(100, self._do_export_and_build_text)

    def _do_export_and_build_text(self):
        """One click from game to a playable .adv disk.

        Mirrors the graphical build: report anything worth knowing, find the
        tools, then tokenise the runtime and write both files to a fresh
        disk image.
        """
        cap_errors, cap_warnings = self.check_capacity()
        compat = self.check_hardware_compat()
        notes = cap_errors + compat + cap_warnings
        if notes:
            msg = "Before building the text disk, a few notes:\n\n"
            msg += "\n".join(f"• {w}" for w in notes)
            msg += "\n\nBuild anyway?"
            if not messagebox.askyesno("Text build notes", msg):
                return

        petcat = self._find_petcat()
        if not petcat:
            messagebox.showerror(
                "petcat not found",
                "petcat tokenises the BASIC runtime and ships with VICE. "
                "Install VICE, or use File > Export .adv and build the disk "
                "by hand — see docs/MANUAL-BUILDS.md section B.")
            return
        c1541 = self._find_c1541()
        if not c1541:
            messagebox.showerror(
                "VICE not found",
                "c1541 builds the disk image and ships with VICE. Install "
                "VICE, or use File > Export .adv for a manual build.")
            return
        runtime = self._kit_basic_runtime()
        if not runtime:
            messagebox.showerror(
                "Runtime missing",
                f"legacy/{self.BASIC_RUNTIME} wasn't found. The text disk "
                f"needs the BASIC player source to tokenise.")
            return

        cfg = self._load_kit_config()
        build_root = cfg.get("build_dir")
        if not build_root or not Path(build_root).exists():
            build_root = filedialog.askdirectory(
                title="Choose a folder to keep your C64 builds in")
            if not build_root:
                return
            cfg["build_dir"] = build_root
            self._save_kit_config(cfg)

        self.root.after(50, lambda: self._run_text_build(
            petcat, c1541, runtime, Path(build_root)))

    def _run_text_build(self, petcat, c1541, runtime, build_root):
        import subprocess
        try:
            slug = slugify(self.game.get("settings", {}).get("title", "game"))
            proj = build_root / f"{slug}-text"
            proj.mkdir(parents=True, exist_ok=True)

            # The .adv needs CR line endings, not LF: the runtime reads a
            # character at a time and ends a line on CHR$(13).
            adv_text = self.generate_adv()
            adv_path = proj / f"{slug}.adv"
            with open(adv_path, "wb") as f:
                for line in adv_text.split("\n"):
                    line = line.rstrip()
                    if line:
                        f.write(line.encode("ascii", "replace") + b"\r")

            # petcat needs lowercase BASIC source, which is how it ships.
            prg = proj / "advplay.prg"
            r = subprocess.run([petcat, "-w2", "-o", str(prg), "--", str(runtime)],
                               capture_output=True, text=True)
            if not prg.exists():
                messagebox.showerror(
                    "Tokenise failed",
                    "petcat could not tokenise the BASIC runtime:\n\n"
                    + ((r.stdout or "") + (r.stderr or ""))[:600])
                return

            disk = proj / "bin" / f"{slug}.d64"
            disk.parent.mkdir(exist_ok=True)
            if disk.exists():
                disk.unlink()
            label = slug[:16]

            def run1541(*args):
                rr = subprocess.run([c1541, *args], capture_output=True, text=True)
                return rr.returncode, (rr.stdout or "") + (rr.stderr or "")

            rc, out = run1541("-format", f"{label},01", "d64", str(disk))
            if not disk.exists():
                messagebox.showerror("Disk build failed",
                                     f"Could not create the disk image:\n{out}")
                return

            # Destination names must be lowercase; c1541 maps uppercase to
            # the wrong PETSCII range.
            rc, out = run1541("-attach", str(disk), "-write", str(prg), "advplay,p")
            if rc != 0:
                messagebox.showerror("Disk build failed",
                                     f"Could not write the player:\n{out}")
                return
            # A 1541 filename is 16 characters, and the runtime asks the
            # player to type it. A truncated slug like "the_haunted_.adv" is
            # unguessable, so the one-click build - which puts one game on
            # one disk - always uses the same short name.
            adv_name = "game.adv"
            rc, out = run1541("-attach", str(disk), "-write", str(adv_path),
                              f"{adv_name},s")
            if rc != 0:
                messagebox.showerror("Disk build failed",
                                     f"Could not write the game file:\n{out}")
                return

            x64sc = self._find_x64sc()
            msg = (f"Your text adventure disk is ready!\n\nDisk image:\n{disk}\n\n"
                   f'On the C64:  LOAD "ADVPLAY",8  then  RUN\n'
                   f"When it asks for the adventure file, enter:\n"
                   f"{adv_name.upper()}")
            if x64sc:
                if messagebox.askyesno("Build complete",
                                       msg + "\n\nPlay it now in VICE?"):
                    subprocess.Popen([x64sc, str(disk)],
                                     stdout=subprocess.DEVNULL,
                                     stderr=subprocess.DEVNULL)
            else:
                messagebox.showinfo("Build complete", msg)
        except Exception as e:
            messagebox.showerror("Build failed", f"Unexpected error: {e}")

    def export_storytllr(self):
        """File > Export StoryTllr Project... — entry point."""
        self.root.after(100, self._do_export_storytllr)

    def _do_export_storytllr(self):
        # Dry-run the converter first: __init__ only analyses, writes nothing.
        try:
            conv = Converter(self.game, crop_offset=STORYTLLR_CROP_OFFSET)
        except Exception as e:
            messagebox.showerror("Export failed", f"Could not analyse game: {e}")
            return

        no_scene = [rid for rid, room in self.game.get("rooms", {}).items()
                    if not room.get("scene_id")]
        advisories = list(dict.fromkeys(conv.warnings))
        if no_scene:
            advisories.append(
                f"{len(no_scene)} room(s) have no scene attached — placeholder "
                f"images will be generated for them.")
        advisories += list(dict.fromkeys(conv.notes))

        if advisories:
            msg = "StoryTllr export notes:\n\n"
            msg += "\n".join(f"• {w}" for w in advisories)
            msg += "\n\nExport anyway?"
            if not messagebox.askyesno("StoryTllr export", msg):
                return
        self.root.after(100, lambda: self._do_export_storytllr_write(conv))

    def _do_export_storytllr_write(self, conv):
        outdir = filedialog.askdirectory(
            title="Choose folder for the StoryTllr project "
                  "(e.g. StoryTllrC64/samples)")
        if not outdir:
            return
        try:
            slug = slugify(self.game.get("settings", {}).get("title", "game"))
            proj = Path(outdir) / slug
            proj.mkdir(parents=True, exist_ok=True)
            # The compiler only auto-creates tmp/ — img/ must exist or the
            # packed room bitmaps are silently not written.
            (proj / "img").mkdir(exist_ok=True)

            script = conv.emit(font_path="..\\shared\\png\\font.png")
            (proj / f"{slug}.hjt").write_text(script, encoding="utf-8")
            images = conv.write_room_images(proj / "png")

            # Find stdlib.hjt: walk up from the output dir (covers exporting
            # into StoryTllrC64/samples), then next to this editor script.
            stdlib_found = False
            probe = Path(outdir).resolve()
            candidates = []
            for _ in range(5):
                candidates.append(probe / "samples" / "accuse" / "stdlib.hjt")
                candidates.append(probe / "samples" / "shared" / "stdlib.hjt")
                candidates.append(probe / "accuse" / "stdlib.hjt")
                candidates.append(probe / "shared" / "stdlib.hjt")
                probe = probe.parent
            candidates.append(Path(__file__).parent / "stdlib.hjt")
            for cand in candidates:
                if cand.exists():
                    shutil.copy(cand, proj / "stdlib.hjt")
                    stdlib_found = True
                    break

            n_placeholder = sum(1 for _, how in images if how == "placeholder")
            note = f"StoryTllr project written to:\n{proj}\n\n"
            note += f"Script: {slug}.hjt\n"
            note += f"Images: {len(images)} room image(s), {n_placeholder} placeholder\n"
            if not stdlib_found:
                note += ("\nWARNING: stdlib.hjt was not found — copy it into "
                         "the project from StoryTllrC64/samples/accuse/ "
                         "before compiling.\n")
            note += ("\nBuild (in Terminal):\n"
                     f"  cd {proj}\n"
                     f"  script_compiler {slug}.hjt tmp.h advcartridge\n"
                     f"  make_d64.sh {slug} <path to storytllr64.prg>\n"
                     f"  x64sc bin/{slug}.d64")
            messagebox.showinfo("Success", note)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to export: {e}")

    def check_hardware_compat(self):
        """
        Scan responses for actions/patterns that advplay-c64-v3.bas can't
        run. Returns a list of human-readable warning strings (empty if
        clean). This is advisory only — it never blocks export by itself.
        """
        warnings = []
        return warnings

    def check_capacity(self):
        """
        Check against advplay-c64-v3.bas's fixed array sizes (its DIM
        statements) and estimate 1541 disk usage.

        Returns (errors, warnings). Errors are hard array-limit overflows
        that cause SILENT DATA LOSS on real hardware — the loader just
        stops parsing more of that type past the limit, with no error
        message at all. Warnings are advisory (disk space estimate).
        """
        # Verified against legacy/advplay-c64-current.bas:
        #   30 dim i$(10)     inventory
        #   40 dim r$(20,4)   rooms
        #   50 dim m$(10,1)   messages   <- 10, not 40
        #   60 dim f$(10)     flags
        #      dim o$(30,4)   objects
        #      dim v$(20,2)   vocabulary
        #      dim rs$(20,3)  responses
        # The loader drops overflow silently: line 4010 reads
        #   nm=nm+1:if nm>10 then return
        # and line 15270 reads
        #   if nf<10 then nf=nf+1
        limits = {
            "rooms":      (len(self.game.get("rooms", {})), 20),
            "objects":    (len(self.game.get("objects", {})), 30),
            "vocabulary": (len(self.game.get("vocabulary", {})), 20),
            "messages":   (len(self.game.get("messages", {})), 10),
            "responses":  (len(self.game.get("responses", [])), 20),
        }
        errors = []
        for label, (count, limit) in limits.items():
            if count > limit:
                errors.append(
                    f"{count} {label}, but advplay-c64-v3.bas only has room "
                    f"for {limit} (its DIM'd array size). Anything past "
                    f"#{limit} is silently dropped on load — no error, it "
                    f"just won't be there."
                )

        warnings = []
        try:
            total = len(self.generate_adv().encode("utf-8"))
            disk_capacity = 170 * 1024  # ~170KB usable on a standard 1541
            if total > disk_capacity:
                warnings.append(
                    f"Estimated size ~{total // 1024}KB (.adv file) "
                    f"exceeds a standard 1541 disk's ~170KB capacity — you'll "
                    f"need to split across disks or trim content/scenes."
                )
            elif total > disk_capacity * 0.85:
                warnings.append(
                    f"Estimated size ~{total // 1024}KB is getting close to "
                    f"a 1541 disk's ~170KB capacity — remember you still need "
                    f"room for the advplay runtime itself alongside it."
                )
        except Exception:
            pass  # size estimate is advisory only; never block export over it

        return errors, warnings

    def _do_export_adv(self):
        cap_errors, cap_warnings = self.check_capacity()
        compat_warnings = self.check_hardware_compat()
        all_warnings = cap_errors + compat_warnings + cap_warnings
        if all_warnings:
            msg = "This game has some issues for real C64 hardware:\n\n"
            msg += "\n".join(f"• {w}" for w in all_warnings)
            msg += "\n\nExport anyway? (The .adv file will still work in this tool's Player tab.)"
            if not messagebox.askyesno("Compatibility warning", msg):
                return
        self.root.after(100, self._do_export_adv_write)

    def _do_export_adv_write(self):
        path = filedialog.asksaveasfilename(defaultextension=".adv",
                                           filetypes=[(".adv files", "*.adv"), ("All files", "*.*")])
        if not path:
            return
        
        try:
            adv_content = self.generate_adv()
            with open(path, 'w') as f:
                f.write(adv_content)

            note = f"Exported to {Path(path).name}"
            note += "\n\n(Text-only export for advplay-c64-v3.bas. For a"
            note += "\ngraphical game, use File > Export StoryTllr Project.)"
            messagebox.showinfo("Success", note)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to export: {e}")
    
    def generate_adv(self):
        lines = []
        
        lines.append("[SETTINGS]")
        for key, value in self.game["settings"].items():
            lines.append(f"{key.upper()}={value}")
        
        lines.append("[ROOMS]")
        lines.append("# Format: ID:Name:Description:North,South,East,West:")
        room_ids = []
        for key in self.game["rooms"].keys():
            try:
                room_ids.append((int(key), key))
            except (ValueError, TypeError):
                room_ids.append((999, key))
        room_ids.sort()
        
        for _, room_id in room_ids:
            room = self.game["rooms"][room_id]
            exits = ",".join(map(str, room["exits"]))
            name = room["name"].upper()
            desc = room["description"].upper()
            lines.append(f"{room_id}:{name}:{desc}:{exits}:")
        
        lines.append("[OBJECTS]")
        lines.append("# Format: ID:StartRoom:Name:Description:Properties")
        for obj_id in sorted(self.game["objects"].keys()):
            obj = self.game["objects"][obj_id]
            start_room = obj["start_room"]
            name = obj["name"].upper()
            desc = obj["description"].upper()
            props = obj["properties"].upper()
            lines.append(f"{obj_id}:{start_room}:{name}:{desc}:{props}")
        
        lines.append("[VOCABULARY]")
        for word, synonyms in self.game["vocabulary"].items():
            lines.append(f"{word.upper()}={','.join(synonyms)}")
        
        lines.append("[MESSAGES]")
        for key, msg in self.game["messages"].items():
            lines.append(f"{key}={msg.upper()}")
        
        lines.append("[RESPONSES]")
        lines.append("# Format: COMMAND:CONDITION:MESSAGE:ACTION")
        for resp in self.game["responses"]:
            line = f"{resp['command']}:{resp['condition']}:{resp['message']}:{resp['action']}"
            lines.append(line)

        # The C64's default character set shows uppercase for codes 0x41-0x5A
        # and graphics for lowercase, so mixed-case text renders as garbage.
        # Author names in particular came through as line noise.
        return "\n".join(lines).upper()

    LEGACY_SYSTEM_MESSAGE_KEYS = (
        "CANT_GO", "DONT_UNDERSTAND", "NOT_HERE", "INVENTORY_EMPTY",
        "ITEM_TAKEN", "ITEM_DROPPED", "WIN_GAME",
    )

    def migrate_messages(self):
        """Move a game off the old system-message table.

        WIN_GAME becomes settings["winmessage"], which both targets read. The
        other six are dropped: the text engine printed its own built-in
        strings and never looked at the table, and only two of the six ever
        reached the graphical build. Custom messages are untouched.
        """
        msgs = self.game.setdefault("messages", {})
        settings = self.game.setdefault("settings", {})
        moved = None
        if msgs.get("WIN_GAME") and not settings.get("winmessage"):
            settings["winmessage"] = msgs["WIN_GAME"]
            moved = msgs["WIN_GAME"]
        dropped = [k for k in self.LEGACY_SYSTEM_MESSAGE_KEYS if k in msgs]
        for k in dropped:
            del msgs[k]
        return moved, dropped

    def refresh_all(self):
        self.migrate_messages()
        self.adopt_undefined_nouns()
        self.refresh_capacity()
        self.map_positions = {}
        self._selected_map_room = None
        self.title_var.set(self.game["settings"].get("title", ""))
        self.author_var.set(self.game["settings"].get("author", ""))
        self.startroom_var.set(str(self.game["settings"].get("startroom", 1)))
        self.maxscore_var.set(str(self.game["settings"].get("maxscore", 100)))
        self.winmessage_var.set(self.game["settings"].get("winmessage", ""))
        self.refresh_rooms_list()
        self.refresh_objects_list()
        self.refresh_vocab_display()
        self.refresh_messages_display()
        self.refresh_responses_display()
        self.refresh_scenes_list()

        # Reset scene UI state after a load
        self._current_scene_id = None
        if hasattr(self, "scene_id_var"):
            self.scene_id_var.set("")
            self.scene_name_var.set("")
            self.scene_preview_label.config(image="", text="(select a scene to preview)")
            self._scene_preview_photo = None
            self.scene_usage_var.set("")
            self.scene_crop_label_var.set("")
            self._suspend_crop_trace = True
            try:
                self.scene_crop_scale.set(CROP_CENTERED)
                self.scene_crop_var.set(CROP_CENTERED)
            finally:
                self._suspend_crop_trace = False
        # Room-editor scene display
        if hasattr(self, "room_scene_display_var"):
            self.room_scene_id = None
            self.room_scene_display_var.set("(none)")


if __name__ == "__main__":
    if tk is None:
        raise SystemExit(
            "The editor needs Tkinter, which this Python cannot import.\n"
            "  Debian/Ubuntu: sudo apt install python3-tk\n"
            "  Fedora:        sudo dnf install python3-tkinter\n"
            "  macOS:         brew install python-tk\n"
            "Check with: python3 -m tkinter"
        )
    root = tk.Tk()
    app = AdventureEditor(root)
    root.mainloop()
