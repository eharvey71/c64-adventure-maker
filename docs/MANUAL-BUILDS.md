# Manual Builds — for when you don't want the one-click path

The editor's **Export & Build C64 Disk** does everything below
automatically. This page is for building by hand, scripting your own
pipeline, or using the original text-only runtime.

## A. Manual StoryTllr build (graphical game)

1. **File → Export StoryTllr Project...** and choose a folder. You get:
   ```
   <game>/
     <game>.hjt        the game script
     stdlib.hjt        engine standard library
     png/              room images (yours + generated placeholders)
     img/              (empty — the compiler fills it)
   ```
2. Compile (note: this compiler exits 1 on success, 0 on error —
   judge by `ERR:` lines, not the exit code):
   ```bash
   cd <game>
   script_compiler <game>.hjt tmp.h advcartridge
   ```
3. Build the disk (all destination names must be lowercase — c1541
   maps uppercase to the wrong PETSCII range):
   ```bash
   c1541 -format "<game>,66" d64 bin/<game>.d64
   c1541 -attach bin/<game>.d64 -write engine/storytllr64.prg <game>
   c1541 -attach bin/<game>.d64 -write img/font font
   c1541 -attach bin/<game>.d64 -write advcartridge advcartridge
   c1541 -attach bin/<game>.d64 -write img/room01 room01
   # ... one -write per img/roomNN file
   ```
4. Play: `x64sc bin/<game>.d64`

### Compiler patches are mandatory

Build `script_compiler` from the
[StoryTllrC64 source](https://github.com/MGProduction/StoryTllrC64) and
apply `tools/fix_storytllr_compiler.sh` **before** compiling games. The
three patches fix upstream bugs:

1. **shortdict split byte** — without it, every dictionary word renders
   as garbage in games whose common-word dictionary is under 256 bytes.
2. **bufferedimgs** — without it, the compiler never writes the
   `img/roomNN` graphics files at all.
3. **all-same shortcut** — without it, images containing a perfectly
   flat color plane (e.g. placeholders) corrupt video memory on the C64.

## B. Text-only build (original BASIC runtime)

The project began as a text-only engine written in C64 BASIC
(`legacy/advplay-c64-v3.bas`). It still works and the editor still
supports it:

1. **File → Export .adv** — writes the plain-text game file.
2. Tokenize the runtime and build a disk (VICE tools):
   ```bash
   petcat -w2 -o advplay.prg -- legacy/advplay-c64-v3.bas
   c1541 -format "adventure,01" d64 mygame.d64 \
         -write advplay.prg advplay \
         -write mygame.adv "mygame.adv,s"
   ```
3. On the C64: `LOAD "ADVPLAY",8` then `RUN`.

BASIC-runtime limits the editor checks for you: 20 rooms, 30 objects,
20 vocabulary entries, 40 messages, 20 responses. Text only — for
graphics, use the StoryTllr path.

## C. Useful gotchas (learned the hard way)

- c1541 destination filenames: **lowercase only**.
- The StoryTllr compiler only auto-creates `tmp/`; `img/` must exist
  before compiling (the editor's exports create it for you).
- Room images must be named `*_C64.png`, or the compiler applies
  dithering/sharpening that corrupts palette-exact images (the editor
  names them correctly).
- Variable names inside the StoryTllr script's `if:` expressions must be
  pure letters — no digits or underscores (the editor's converter
  handles this automatically).
