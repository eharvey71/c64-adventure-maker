# C64 Adventure Maker

[![CI](https://github.com/eharvey71/c64-adventure-maker/actions/workflows/ci.yml/badge.svg)](https://github.com/eharvey71/c64-adventure-maker/actions/workflows/ci.yml)

Make **graphical text adventures for the Commodore 64**. Design your game in
a friendly cross-platform editor, test it instantly, then build a
ready-to-play `.d64` disk image with one menu click — playable in the VICE
emulator or on real hardware.

![workflow] Design in the editor → **File → Export & Build C64 Disk** → play.

## Features

- **Full game editor** — rooms, objects, vocabulary, messages, and
  responses, with a visual room map
- **Instant playtesting** — a built-in Player tab runs your game as you
  edit it, with a debug mode that shows exactly how commands are parsed
- **Room graphics** — import C64 Koala images (from Multipaint,
  Retropixels, Dithertron, ...) in the Scenes tab and attach them to rooms;
  they appear on the C64's split screen. The C64 shows a 96-row band of
  each 200-row image, so the Scenes tab has a **visible band** slider and
  dims the rows that won't ship — the preview matches the built disk.
  Rooms without art get a clean colored placeholder automatically
- **One-click C64 build** — converts, compiles, and builds the `.d64`,
  then offers to launch it in VICE
- **No Python dependencies** — the editor uses only the standard library
  (Tkinter)

The C64 side is powered by the excellent
[StoryTllrC64](https://github.com/MGProduction/StoryTllrC64) engine by
Marco Giorgini (MIT license) — see `engine/ATTRIBUTION.md`.

## What you need

1. **Python 3.8+** with Tkinter (`python3 -m tkinter` should open a window)
2. **[VICE](https://vice-emu.sourceforge.io/)** — provides `c1541`
   (builds disk images) and `x64sc` (plays them).
   macOS: `brew install vice` · Debian/Ubuntu: `sudo apt install vice`
   The editor finds them on `PATH` or in the usual install locations on
   macOS, Linux, and Windows; otherwise it asks once and remembers.
3. **A C compiler** (macOS: `xcode-select --install`) — used once by
   the setup script below to build the StoryTllr `script_compiler`.

## Quick start

One-time setup — builds the game compiler (downloads the StoryTllrC64
source, applies the required patches, compiles):

```bash
sh tools/setup_compiler.sh
```

Then run the editor:

```bash
python3 adventure_editor_v7.py
```

Open `example_castle.json` (File → Open) to explore a complete sample
game, or start fresh. When you're ready:

**File → Export & Build C64 Disk...**

The first time, you'll be asked where to keep your builds (and to locate
`script_compiler` if it isn't in `tools/`). After that it's fully
automatic: your finished disk lands at
`<builds folder>/<game name>/bin/<game name>.d64` and the editor offers
to launch it in VICE.

See **[docs/QUICKSTART.md](docs/QUICKSTART.md)** for a 5-minute
first-game walkthrough, **[docs/PLAYER_GUIDE.md](docs/PLAYER_GUIDE.md)**
for the game-logic reference (conditions, actions, debugging), and
**[docs/MANUAL-BUILDS.md](docs/MANUAL-BUILDS.md)** for building without
the one-click path (including the text-only `.adv` export for the
original BASIC runtime).

## Repository layout

```
adventure_editor_v7.py    the editor
example_castle.json       sample game
engine/                   bundled StoryTllrC64 runtime files
                          (player program, standard library, font)
tools/                    compiler setup + patch scripts; the built
                          script_compiler lands here (not committed)
tests/                    converter and game-engine tests
docs/                     guides
legacy/                   reserved for the original text-only BASIC
                          runtime (not committed yet)
```

## Development

```bash
python3 -m unittest discover -s tests
```

The converter and game-engine layers import without Tkinter, so the tests
run headless. `tests/golden/example_castle.hjt` pins the exact StoryTllr
script produced from `example_castle.json`; if you change the converter
deliberately, regenerate it with `python3 tests/update_golden.py` and
review the diff.

CI byte-compiles the editor and runs the tests (GUI smoke tests
included, under Xvfb) on Python 3.9–3.13,
enforces the 3.8 syntax floor, shellchecks `tools/*.sh`, and builds
`script_compiler` from the pinned StoryTllrC64 commit on Linux and macOS.

## Running your game on real hardware

The `.d64` works on a real C64 via an SD2IEC, Ultimate-II cartridge,
Kung Fu Flash, or a real 1541 drive with a transfer cable.

## License

MIT — see [LICENSE](LICENSE).

Bundled engine files in `engine/` are MIT as well: StoryTllrC64
© Marco Giorgini (`engine/ATTRIBUTION.md`).
