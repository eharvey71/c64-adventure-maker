"""Build Commodore 64 files in pure Python: no VICE needed.

Two jobs the text build used to hand to VICE's command-line tools:

  tokenize_basic()  turns BASIC V2 source into a loadable .prg, the way
                    `petcat -w2` does.
  D64               lays files out on a 1541 disk image, the way
                    `c1541 -format ... -write ...` does.

Both are checked byte for byte against VICE 3.7.1 by
tests/test_c64build.py (which skips that comparison where VICE isn't
installed). Where petcat or c1541 silently produce something a C64 can't
use, these raise an error instead; each such case is noted below.
"""

LOAD_ADDRESS = 0x0801       # start of BASIC on the C64
MAX_LINE_NUMBER = 63999     # BASIC V2's limit


class BasicError(ValueError):
    """The BASIC source can't be tokenised."""


class DiskError(ValueError):
    """The file can't be placed on the disk."""


# ---------------------------------------------------------------- BASIC --

# BASIC V2 keywords in token order, 0x80 upward. See _match_keyword for
# how petcat picks among them.
_KEYWORDS = (
    "end", "for", "next", "data", "input#", "input", "dim", "read", "let",
    "goto", "run", "if", "restore", "gosub", "return", "rem", "stop", "on",
    "wait", "load", "save", "verify", "def", "poke", "print#", "print",
    "cont", "list", "clr", "cmd", "sys", "open", "close", "get", "new",
    "tab(", "to", "fn", "spc(", "then", "not", "step", "+", "-", "*", "/",
    "^", "and", "or", ">", "=", "<", "sgn", "int", "abs", "usr", "fre",
    "pos", "sqr", "rnd", "log", "exp", "cos", "sin", "tan", "atn", "peek",
    "len", "str$", "val", "asc", "chr$", "left$", "right$", "mid$", "go",
)
_DATA = 0x80 + _KEYWORDS.index("data")
_REM = 0x80 + _KEYWORDS.index("rem")

# {name} control codes, as petcat spells them. Only inside quotes: outside
# a string, petcat leaves "{clr}" as the literal characters. Each name is
# accepted in lowercase or all-uppercase; {$hh} and {decimal} give any byte.
_CONTROL = {
    "stop": 0x03, "wht": 0x05, "white": 0x05, "dish": 0x08, "ensh": 0x09,
    "down": 0x11, "rvon": 0x12, "home": 0x13, "del": 0x14, "esc": 0x1B,
    "red": 0x1C, "rght": 0x1D, "right": 0x1D, "grn": 0x1E, "green": 0x1E,
    "blu": 0x1F, "blue": 0x1F, "space": 0x20, "return": 0x0D,
    "swlc": 0x0E, "lower case": 0x0E, "orng": 0x81, "orange": 0x81,
    "f1": 0x85, "f3": 0x86, "f5": 0x87, "f7": 0x88, "f2": 0x89, "f4": 0x8A,
    "f6": 0x8B, "f8": 0x8C, "sret": 0x8D, "swuc": 0x8E, "upper case": 0x8E,
    "blk": 0x90, "black": 0x90, "up": 0x91, "rvof": 0x92, "clr": 0x93,
    "clear": 0x93, "inst": 0x94, "brn": 0x95, "brown": 0x95, "lred": 0x96,
    "pink": 0x96, "gry1": 0x97, "gry2": 0x98, "lgrn": 0x99, "lblu": 0x9A,
    "gry3": 0x9B, "pur": 0x9C, "purple": 0x9C, "left": 0x9D, "yel": 0x9E,
    "yellow": 0x9E, "cyn": 0x9F, "cyan": 0x9F,
}


def _petscii(ch, lineno):
    """ASCII -> PETSCII as petcat's _a_topetscii() does it."""
    c = ord(ch)
    if c == 0x7E:                 # ~ is pi
        return 0xFF
    if 0x5B <= c <= 0x5F:         # [ \ ] ^ _  unchanged
        return c
    if 0x60 <= c <= 0x7E:         # ` a-z { | }  -> unshifted
        return c ^ 0x20
    if 0x41 <= c <= 0x5A:         # A-Z -> shifted letters
        return c | 0x80
    if c == 0x09 or 0x20 <= c <= 0x40:
        return c
    raise BasicError(f"line {lineno}: character {ch!r} has no PETSCII "
                     f"equivalent")


def _control(name, lineno):
    if name in _CONTROL or (name.isupper() and name.lower() in _CONTROL):
        return _CONTROL[name.lower()]
    try:
        value = int(name[1:], 16) if name.startswith("$") else int(name, 10)
    except ValueError:
        value = -1
    if 0 <= value <= 0xFF:
        return value
    raise BasicError(f"line {lineno}: unknown control code {{{name}}}")


def _match_keyword(text, i):
    """The keyword starting at text[i], as petcat's sstrcmp() finds it.

    A keyword matches if its lowercase spelling appears in full, or as an
    abbreviation: one or more of its letters followed by the next letter in
    uppercase (the C64's "pR" style). Of all matches, the longest wins, and
    on a tie the one later in the table: "tA" could be TAB( or TAN, and
    petcat takes TAN. Returns (token, length) or (None, 0).
    """
    best, best_len = None, 1
    for token, kw in enumerate(_KEYWORDS, 0x80):
        j = 0
        while j < len(kw) and i + j < len(text) and kw[j] == text[i + j]:
            j += 1
        if not j:
            continue
        if j < len(kw):
            if i + j < len(text) and ord(kw[j]) ^ ord(text[i + j]) == 0x20:
                j += 1
            else:
                continue
        if j >= best_len:
            best, best_len = token, j
    return (best, best_len) if best is not None else (None, 0)


def _tokenize_line(text, lineno):
    out = bytearray()
    quote = data = rem = False
    i = 0
    while i < len(text):
        ch = text[i]
        if ch == "{" and quote:
            end = text.find("}", i)
            if end < 0:
                raise BasicError(f"line {lineno}: '{{' without a closing '}}'")
            out.append(_control(text[i + 1:end], lineno))
            i = end + 1
            continue
        if ch == '"':
            quote = not quote
            out.append(0x22)
            i += 1
            continue
        if rem or quote or data:
            # petcat ends DATA at any colon, even one inside quotes; the
            # C64's own editor doesn't, but petcat built the runtime that
            # has been verified on hardware, so it is the reference.
            if data and ch == ":":
                data = False
            out.append(_petscii(ch, lineno))
            i += 1
            continue
        token, length = (_match_keyword(text, i)
                         if ch.isalpha() or ch in "+-*/^>=<" else (None, 0))
        if token is not None:
            out.append(token)
            i += length
            rem = token == _REM
            data = token == _DATA
        else:
            out.append(_petscii(ch, lineno))
            i += 1
    return bytes(out)


def tokenize_basic(source, load_address=LOAD_ADDRESS):
    """Tokenise BASIC V2 source (lowercase keywords) into .prg bytes.

    Byte-identical to `petcat -w2` for valid input. A line starting with
    ";" is a comment and is skipped, as in petcat. Two things petcat
    accepts are errors here: a line with no line number (petcat quietly
    numbers it two past the previous line) and a line number above 63999
    (which a C64 can't list or run).
    """
    lines = []
    for n, raw in enumerate(source.splitlines(), 1):
        raw = raw.rstrip("\r\n")
        if raw.startswith(";"):
            continue
        stripped = raw.lstrip(" \t")
        if not stripped:
            continue
        digits = len(stripped) - len(stripped.lstrip("0123456789"))
        if not digits:
            raise BasicError(f"source line {n} has no line number: {raw!r}")
        lineno = int(stripped[:digits])
        if lineno > MAX_LINE_NUMBER:
            raise BasicError(f"line number {lineno} is above {MAX_LINE_NUMBER}")
        body = stripped[digits:].lstrip(" \t")
        if body:                      # petcat drops a bare line number
            lines.append((lineno, _tokenize_line(body, lineno)))

    out = bytearray(load_address.to_bytes(2, "little"))
    address = load_address
    for lineno, body in lines:
        address += 2 + 2 + len(body) + 1
        if address > 0xFFFF:
            raise BasicError("program is too large for C64 memory")
        out += address.to_bytes(2, "little")
        out += lineno.to_bytes(2, "little")
        out += body + b"\x00"
    out += b"\x00\x00"
    return bytes(out)


# ------------------------------------------------------------------ D64 --

SECTORS_PER_TRACK = [21] * 17 + [19] * 7 + [18] * 6 + [17] * 5   # tracks 1-35
DIR_TRACK = 18
INTERLEAVE = 10             # data sectors, as c1541 places them
DIR_INTERLEAVE = 3          # directory sectors
D64_SIZE = sum(SECTORS_PER_TRACK) * 256      # 174848
_FILE_TYPES = {"del": 0x80, "seq": 0x81, "prg": 0x82, "usr": 0x83}


def _petscii_name(text, what):
    out = bytearray()
    for ch in text:
        if "a" <= ch <= "z":
            out.append(ord(ch) - 0x20)
        elif "A" <= ch <= "Z":
            out.append(ord(ch) + 0x80)
        elif ch in " !#$%&'()+-./0123456789;<=>@[]^_":
            out.append(ord(ch))
        else:
            raise DiskError(f"{what} {text!r}: {ch!r} can't be used")
    if not 0 < len(out) <= 16:
        raise DiskError(f"{what} {text!r} must be 1-16 characters")
    return bytes(out) + b"\xa0" * (16 - len(out))


class D64:
    """A 1541 disk image, laid out exactly as c1541 lays it out."""

    def __init__(self, label, disk_id="01"):
        if len(disk_id) != 2:
            raise DiskError("the disk ID must be two characters")
        self.image = bytearray(D64_SIZE)
        self.free = [set(range(n)) for n in SECTORS_PER_TRACK]
        self._use(DIR_TRACK, 0)
        self._use(DIR_TRACK, 1)
        bam = bytearray(256)
        bam[0:4] = bytes([DIR_TRACK, 1, 0x41, 0x00])
        bam[0x90:0xA0] = _petscii_name(label, "disk label")
        bam[0xA0:0xAB] = (b"\xa0\xa0" + _petscii_name(disk_id, "disk ID")[:2]
                          + b"\xa0" + b"2A" + b"\xa0" * 4)
        self._bam = bam
        self._write(DIR_TRACK, 1, b"\x00\xff" + bytes(254))
        self._dir_sectors = [1]

    # -- low level --

    @staticmethod
    def _offset(track, sector):
        return (sum(SECTORS_PER_TRACK[:track - 1]) + sector) * 256

    def _read(self, track, sector):
        o = self._offset(track, sector)
        return bytes(self.image[o:o + 256])

    def _write(self, track, sector, data):
        o = self._offset(track, sector)
        self.image[o:o + 256] = data

    def _use(self, track, sector):
        self.free[track - 1].discard(sector)

    def _is_free(self, track, sector):
        return sector in self.free[track - 1]

    # -- allocation, matching VICE's vdrive --

    def _first_sector(self):
        """Where a new file starts: the nearest track to the directory,
        below then above, at its lowest free sector."""
        for d in range(1, 35):
            for t in (DIR_TRACK - d, DIR_TRACK + d):
                if 1 <= t <= 35 and self.free[t - 1]:
                    s = min(self.free[t - 1])
                    self._use(t, s)
                    return t, s
        raise DiskError("the disk is full")

    def _step(self, track, sector, interleave=INTERLEAVE):
        """Advance `sector` by the interleave on `track`, wrapping as the
        1541 does: past the end, subtract the track's length and then one
        more unless that lands on sector 0."""
        n = SECTORS_PER_TRACK[track - 1]
        s = sector + interleave
        if s >= n:
            s -= n
            if s:
                s -= 1
        return s

    def _claim_from(self, track, sector):
        n = SECTORS_PER_TRACK[track - 1]
        s = sector
        for _ in range(n):
            if self._is_free(track, s):
                self._use(track, s)
                return s
            s = s + 1 if s + 1 < n else 0
        return None

    def _next_sector(self, track, sector):
        """The sector after (track, sector) in a file's chain."""
        t, s = track, sector
        for _side in range(2):
            step = -1 if t < DIR_TRACK else 1
            while 1 <= t <= 35:
                if t != DIR_TRACK and self.free[t - 1]:
                    got = self._claim_from(t, min(self._step(t, s),
                                                  SECTORS_PER_TRACK[t - 1] - 1))
                    return t, got
                t += step
            # This side is full: carry on from the directory on the other
            # side, as if the previous sector were sector 0 of track 18.
            t, s = DIR_TRACK - step, 0
        raise DiskError("the disk is full")

    # -- files --

    def add_file(self, name, data, kind="prg"):
        """Write a file. `kind` is prg, seq, usr or del."""
        if kind not in _FILE_TYPES:
            raise DiskError(f"unknown file type {kind!r}")
        pname = _petscii_name(name, "file name")
        slot = self._directory_slot()
        chunks = [data[i:i + 254] for i in range(0, len(data), 254)] or [b""]
        first = track, sector = self._first_sector()
        buf = bytearray(256)                 # reused, as c1541 does
        for i, chunk in enumerate(chunks):
            buf[2:2 + len(chunk)] = chunk
            if i + 1 < len(chunks):
                nt, ns = self._next_sector(track, sector)
                buf[0], buf[1] = nt, ns
            else:
                buf[0], buf[1] = 0, len(chunk) + 1
            self._write(track, sector, buf)
            if i + 1 < len(chunks):
                track, sector = nt, ns
        self._fill_entry(slot, _FILE_TYPES[kind], first, pname, len(chunks))

    def _directory_slot(self):
        for ds in self._dir_sectors:
            sec = self._read(DIR_TRACK, ds)
            for e in range(8):
                if sec[e * 32 + 2] == 0:
                    return ds, e
        last = self._dir_sectors[-1]
        new = self._claim_from(DIR_TRACK,
                               self._step(DIR_TRACK, last, DIR_INTERLEAVE))
        if new is None:
            raise DiskError("the directory is full")
        prev = bytearray(self._read(DIR_TRACK, last))
        prev[0], prev[1] = DIR_TRACK, new
        self._write(DIR_TRACK, last, prev)
        self._write(DIR_TRACK, new, b"\x00\xff" + bytes(254))
        self._dir_sectors.append(new)
        return new, 0

    def _fill_entry(self, slot, ftype, first, pname, blocks):
        ds, e = slot
        sec = bytearray(self._read(DIR_TRACK, ds))
        entry = bytearray(30)
        entry[0] = ftype
        entry[1], entry[2] = first
        entry[3:19] = pname
        entry[28:30] = blocks.to_bytes(2, "little")
        sec[e * 32 + 2:e * 32 + 32] = entry
        self._write(DIR_TRACK, ds, sec)

    # -- output --

    def to_bytes(self):
        bam = bytearray(self._bam)
        for t in range(1, 36):
            free = self.free[t - 1]
            bits = sum(1 << s for s in free)
            bam[4 * t:4 * t + 4] = bytes([len(free), bits & 0xFF,
                                          bits >> 8 & 0xFF, bits >> 16 & 0xFF])
        image = bytearray(self.image)
        o = self._offset(DIR_TRACK, 0)
        image[o:o + 256] = bam
        return bytes(image)

    def save(self, path):
        with open(path, "wb") as f:
            f.write(self.to_bytes())
