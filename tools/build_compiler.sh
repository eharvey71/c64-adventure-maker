#!/bin/bash
# Build StoryTllrC64's script_compiler natively on macOS/Linux.
# Usage: ./build_compiler.sh /path/to/StoryTllrC64
set -e
REPO="${1:?Usage: ./build_compiler.sh /path/to/StoryTllrC64}"
SHIM="$(cd "$(dirname "$0")" && pwd)"
# GCC 14 made passing a mismatched pointer type an error rather than a
# warning, and -w only silences warnings. StoryTllr's main.c does this in
# four places; GCC 13 and Clang compile them with a warning, so this flag
# keeps GCC 14 building the same binary instead of refusing.
# Set CC to choose a compiler (e.g. CC=clang).
"${CC:-cc}" -O2 -w -Wno-error=incompatible-pointer-types \
   -I"$SHIM" -include "$SHIM/windows.h" \
   -o "$SHIM/script_compiler" \
   "$REPO/compiler/main.c" \
   "$REPO/compiler/image_en.c" \
   "$SHIM/imageshow_stub.c" \
   -lm
echo "Built: $SHIM/script_compiler"
