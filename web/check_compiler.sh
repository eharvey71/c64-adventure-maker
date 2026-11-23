#!/bin/bash
# Checks the WebAssembly build of StoryTllr's compiler without a browser:
# builds it for Node, compiles a game with it and with the native
# tools/script_compiler, and compares every file the two write.
#
#   bash web/check_compiler.sh [game.json]
#   OPT="-O1" bash web/check_compiler.sh      # try other compiler flags
set -e
WEB="$(cd "$(dirname "$0")" && pwd)"
REPO="$(dirname "$WEB")"
SRC="$REPO/tools/StoryTllrC64-src"
GAME="${1:-$REPO/example_castle.json}"
OPT="${OPT:--O2}"
WORK="$(mktemp -d)"
cd "$REPO"

# shellcheck disable=SC2086  # OPT is a list of flags
emcc $OPT -w -Wno-error=incompatible-pointer-types -I"$REPO/tools" \
     -include "$REPO/tools/windows.h" -Dmain=storytllr_main \
     "$SRC/compiler/main.c" "$SRC/compiler/image_en.c" \
     "$REPO/tools/imageshow_stub.c" "$WEB/wasm_entry.c" \
     -sNODERAWFS=1 -sALLOW_MEMORY_GROWTH=1 -sMODULARIZE=1 \
     -sEXPORTED_FUNCTIONS=_compile_game -sEXPORTED_RUNTIME_METHODS=ccall \
     -o "$WORK/compiler.js" -lm

for side in native wasm; do
  python3 - "$GAME" "$WORK/$side" <<'PY'
import json, sys
from pathlib import Path
sys.path.insert(0, ".")
import adventure_editor_v7 as ed
game = json.loads(Path(sys.argv[1]).read_text())
print(ed.prepare_graphical_project(game, sys.argv[2], "engine/stdlib.hjt",
                                   font_png="engine/font.png"))
PY
done > "$WORK/script_names"
SCRIPT="$(head -1 "$WORK/script_names")"

# The native compiler exits 1 on success, so judge it by what it writes.
(cd "$WORK/native" && "$REPO/tools/script_compiler" "$SCRIPT" tmp.h advcartridge >/dev/null || true)
[ -f "$WORK/native/advcartridge" ] || { echo "the native compiler wrote no game" >&2; exit 1; }
timeout "${TIMEOUT:-60}" node "$WEB/run_compiler_node.cjs" "$WORK/compiler.js" "$WORK/wasm" "$SCRIPT" >/dev/null \
  || { echo "FAIL ($OPT): the WebAssembly compiler didn't finish within ${TIMEOUT:-60}s"; exit 1; }

if diff -rq "$WORK/native" "$WORK/wasm"; then
  echo "PASS ($OPT): every file matches the native compiler's"
else
  echo "FAIL ($OPT): the files above differ from the native compiler's"
  exit 1
fi
