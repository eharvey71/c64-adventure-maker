#!/bin/bash
# Builds the in-browser proof into web/dist/:
#   - StoryTllr's compiler as WebAssembly (needs Emscripten's emcc)
#   - Pyodide (from npm), the editor's Python files, engine files, the sample
# Run tools/setup_compiler.sh first: it fetches and patches the compiler source.
set -e
WEB="$(cd "$(dirname "$0")" && pwd)"
REPO="$(dirname "$WEB")"
SRC="$REPO/tools/StoryTllrC64-src"
OBJ="$WEB/build"
DIST="$WEB/dist"

if [ ! -f "$SRC/compiler/main.c" ]; then
  echo "Compiler source not found. Run: sh tools/setup_compiler.sh" >&2
  exit 1
fi
command -v emcc >/dev/null || { echo "emcc (Emscripten) not found" >&2; exit 1; }

mkdir -p "$OBJ" "$DIST/compiler" "$DIST/repo/engine" "$DIST/repo/legacy"

# Same flags as tools/build_compiler.sh. main() is renamed so the page can
# call compile_game() by name (see wasm_entry.c).
FLAGS=(-O2 -w -Wno-error=incompatible-pointer-types -I"$REPO/tools"
       -include "$REPO/tools/windows.h")
emcc "${FLAGS[@]}" -Dmain=storytllr_main -c "$SRC/compiler/main.c" -o "$OBJ/main.o"
emcc "${FLAGS[@]}" -c "$SRC/compiler/image_en.c" -o "$OBJ/image_en.o"
emcc -O2 -w -c "$REPO/tools/imageshow_stub.c" -o "$OBJ/stub.o"
emcc -O2 -c "$WEB/wasm_entry.c" -o "$OBJ/entry.o"
# StoryTllr's compiler keeps large buffers on the stack. Emscripten's
# default stack is 64 KB in current versions (it was 5 MB in old ones), and
# overflowing it corrupts memory: the compiler hung. 8 MB is ample.
# TOTAL_STACK is the older spelling of STACK_SIZE, and both versions accept it.
emcc -O2 -sALLOW_MEMORY_GROWTH=1 -sTOTAL_STACK=8MB -sMODULARIZE=1 -sEXPORT_NAME=createCompiler \
     -sENVIRONMENT=web -sFORCE_FILESYSTEM=1 \
     "-sINCOMING_MODULE_JS_API=['print','printErr']" \
     -sEXPORTED_FUNCTIONS=_compile_game -sEXPORTED_RUNTIME_METHODS=ccall,FS \
     -o "$DIST/compiler/compiler.js" \
     "$OBJ/main.o" "$OBJ/image_en.o" "$OBJ/stub.o" "$OBJ/entry.o" -lm

# Pyodide, pinned in package.json.
if [ ! -d "$WEB/node_modules/pyodide" ]; then
  (cd "$WEB" && npm install --no-audit --no-fund)
fi
mkdir -p "$DIST/pyodide"
cp -R "$WEB/node_modules/pyodide/." "$DIST/pyodide/"

# The editor's own code and the files a build needs.
cp "$REPO/adventure_editor_v7.py" "$REPO/c64build.py" "$DIST/repo/"
cp "$REPO/engine/font.png" "$REPO/engine/stdlib.hjt" \
   "$REPO/engine/storytllr64.prg" "$DIST/repo/engine/"
cp "$REPO/legacy/advplay-c64-current.bas" "$DIST/repo/legacy/"
cp "$REPO/example_castle.json" "$DIST/"
cp "$WEB/index.html" "$WEB/editor.html" "$DIST/"
mkdir -p "$DIST/editor"
cp "$WEB/editor/"*.js "$WEB/editor/"*.css "$DIST/editor/"

echo "Built $DIST"
