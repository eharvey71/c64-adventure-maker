# Browser build proof

Evidence that the editor's builds can run entirely in a web browser, with no
server. This is a proof, not the web version: there is no editing UI yet.

## What it shows

In headless Chromium, `index.html`:

1. loads **Pyodide** (Python compiled to WebAssembly) and the editor's own
   `adventure_editor_v7.py` and `c64build.py`, unchanged;
2. calls the same build functions the desktop editor uses,
   `build_graphical_disk` and `build_text_disk`;
3. hands `build_graphical_disk` a JavaScript function as its compiler,
   which runs **StoryTllr's compiler built as WebAssembly**.

`test_browser.cjs` then compares both disks with the ones the desktop
editor builds (`reference.py`, which runs the editor's real build
functions). Results when this was saved:

| Game | Text disk | Graphical disk | Time in browser |
|---|---|---|---|
| `example_castle.json` | identical | identical | 2.7 s |
| the castle with full-size Koala art on every room | identical | identical | 2.9 s |

The compiler was also checked on its own: run as WebAssembly under Node, it
wrote exactly the same files as the native `tools/script_compiler` (the
compiled game, font, every room image and the generated headers).

## Running it

Needs Emscripten (`emcc`), Node, and the patched compiler source:

```bash
sh tools/setup_compiler.sh        # once: fetches and patches the compiler
bash web/build.sh                 # builds web/dist/
npm install --no-save playwright && npx playwright install chromium
node web/test_browser.cjs                    # the sample castle
node web/test_browser.cjs path/to/game.json  # any game
```

To look at it yourself, serve `web/dist/` with any static file server (for
example `python3 -m http.server -d web/dist`) and open `index.html`; the
page prints both disk hashes when it finishes.

## How the compiler is built

`build.sh` uses the same flags as `tools/build_compiler.sh`, plus:

- `-Dmain=storytllr_main` and `wasm_entry.c`: the compiler's command-line
  `main` becomes an ordinary function, and the page calls
  `compile_game(script, header, cartridge)` by name.
- `MODULARIZE` with `FORCE_FILESYSTEM`: each build creates a fresh compiler
  instance with an in-memory file system the page fills and reads back.

## Caveats

- **Toolchain.** The proof was built with Ubuntu's Emscripten 3.1.6, which
  pairs an old Emscripten with Clang 15; its linker didn't recognise Clang's
  renamed `main` and silently dropped the whole compiler. The named entry
  point above avoids that. A current Emscripten (e.g. `brew install
  emscripten`) should work as well but hasn't been verified yet: run the
  test above to check.
- **Download size.** Pyodide is about 14 MB on the first visit; browsers
  cache it after that.
- **Browsers.** Tested in Chromium only, not Safari or Firefox.
- **One build per compiler instance.** The page creates a fresh compiler for
  each build. Several builds in one instance haven't been tested; the
  compiler keeps global state.
