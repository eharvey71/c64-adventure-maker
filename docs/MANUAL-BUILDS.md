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

The project began as a text-only engine written in C64 BASIC. Its current
runtime is `legacy/advplay-c64-current.bas`.

**File → Export & Build C64 Disk (text only)...** does the whole build in
one step and needs no VICE: the editor tokenises the runtime and writes the
`.d64` itself (`c64build.py`, byte-identical to `petcat` and `c1541`). On
the C64: `LOAD "ADVPLAY",8` then `RUN`, and enter `GAME` when asked for the
adventure file.

To build by hand with VICE instead:

1. **File → Export .adv** — writes the game file.
2. Convert its line endings. The export uses ordinary newlines, but the
   runtime reads one character at a time and ends a line on a carriage
   return:
   ```bash
   python3 -c "import sys; t=open(sys.argv[1]).read(); open(sys.argv[2],'wb').write(b''.join(l.rstrip().encode('ascii')+b'\r' for l in t.split('\n') if l.rstrip()))" mygame.adv mygame-cr.adv
   ```
3. Tokenise the runtime and build a disk:
   ```bash
   petcat -w2 -o advplay.prg -- legacy/advplay-c64-current.bas
   c1541 -format "adventure,01" d64 mygame.d64 \
         -write advplay.prg advplay \
         -write mygame-cr.adv "game.adv,s"
   ```

BASIC-runtime limits, shown as counters in the editor: 20 rooms, 30
objects, 20 vocabulary entries, 20 responses, 10 messages, 10 flags.
Text only — for graphics, use the StoryTllr path.

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
