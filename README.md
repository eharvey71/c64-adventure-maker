# C64 Adventure Maker

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
  they appear on the C64's split screen. Rooms without art get a clean
  colored placeholder automatically
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
   macOS: `brew install vice`
3. **The StoryTllr `script_compiler`** — built once from the
   [StoryTllrC64 source](https://github.com/MGProduction/StoryTllrC64)
   **with the patches in `tools/fix_storytllr_compiler.sh` applied**
   (they fix three upstream bugs that otherwise garble text and corrupt
   or omit graphics). Copy the built binary into this repo's `tools/`
   folder — the editor finds it there automatically.

## Quick start

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
tools/                    compiler patch script; put your built
                          script_compiler here (not committed)
docs/                     guides
legacy/                   the original text-only BASIC runtime era
```

## Running your game on real hardware

The `.d64` works on a real C64 via an SD2IEC, Ultimate-II cartridge,
Kung Fu Flash, or a real 1541 drive with a transfer cable.

## License

Editor and converter: use and modify freely.
Bundled engine files: MIT — StoryTllrC64 © Marco Giorgini
(`engine/ATTRIBUTION.md`).
