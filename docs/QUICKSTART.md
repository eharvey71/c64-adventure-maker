# Quick Start — your first C64 adventure in 5 minutes

## Run the editor

First time on this machine? Build the game compiler once:

```bash
sh tools/setup_compiler.sh
```

Then:

```bash
python3 adventure_editor_v7.py
```

## Build a tiny game

1. **File → New Game**. Set a title ("MY FIRST ADVENTURE") and author in
   the top bar.

2. **Rooms tab.** Room 1 exists already — name it `STARTING ROOM`,
   description `YOU ARE IN A MYSTERIOUS ROOM.`, and set its **South**
   exit to `2`. Click **+ New** for room 2: name `TREASURE CHAMBER`,
   description `GOLD GLITTERS EVERYWHERE!`, **North** exit `1`.

3. **Objects tab.** **+ New**: ID `GOLD`, name `GOLD COIN`, start room
   `2`, description `A SHINY GOLD COIN.`, properties `TAKEABLE`.

4. **Responses tab.** Add:
   ```
   TAKE GOLD:AT 2:YOU GRAB THE COIN. YOU WIN!:SCORE 100,WINXXX
   ```

5. **Test it now** — Player tab → **Start Game**. Type `s`, then
   `take gold`. You should win. (Toggle **Debug** to see how each
   command is parsed if something doesn't work.)

## Add a picture (optional)

1. Make a C64 Koala image (160×200) in
   [Multipaint](http://multipaint.kameli.net/),
   [Retropixels](https://www.micheldebree.nl/retropixels/), or
   [Dithertron](https://8bitworkshop.com/dithertron/) and save/export as
   Koala (`.koa`/`.kla`).
2. **Scenes tab → Import Scene**, pick the file, give it a name.
3. **Rooms tab** — select a room and choose the scene in its Scene
   dropdown.

Rooms without a scene automatically get a simple colored placeholder —
you can ship a game before the artwork is done. Note: the C64 shows the
**top 96 of the image's 200 rows** on its split screen, so compose the
important part of the picture in the upper half.

## Build the C64 disk

**File → Export & Build C64 Disk...**

- First time only: it asks where to keep builds, and to locate
  `script_compiler` if it isn't in the kit's `tools/` folder.
- It converts the game, compiles it, and builds
  `<builds>/<game>/bin/<game>.d64` — then offers to launch VICE.

That disk is the finished product: load it in any C64 emulator or copy
it to real hardware.

## If something goes wrong

- **"I couldn't find the StoryTllr compiler"** — run
  `sh tools/setup_compiler.sh` once.
- **"VICE not found"** — install VICE; on macOS `brew install vice`.
- **Garbled text or broken pictures on the C64** — your compiler is
  missing the required patches; run `tools/fix_storytllr_compiler.sh`
  against the StoryTllrC64 source and rebuild it.
- **A response doesn't fire in the game** — use the Player tab's Debug
  mode; it shows the parse, the matched rule, and the condition results.
