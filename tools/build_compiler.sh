#!/bin/bash
# Build StoryTllrC64's script_compiler natively on macOS/Linux.
# Usage: ./build_compiler.sh /path/to/StoryTllrC64
set -e
REPO="${1:?Usage: ./build_compiler.sh /path/to/StoryTllrC64}"
SHIM="$(cd "$(dirname "$0")" && pwd)"
cc -O2 -w -I"$SHIM" -include "$SHIM/windows.h" \
   -o "$SHIM/script_compiler" \
   "$REPO/compiler/main.c" \
   "$REPO/compiler/image_en.c" \
   "$SHIM/imageshow_stub.c" \
   -lm
echo "Built: $SHIM/script_compiler"
