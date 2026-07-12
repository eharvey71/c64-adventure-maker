#!/bin/bash
# One-command compiler setup for a fresh machine (macOS or Linux).
# Downloads the StoryTllrC64 source, applies the required patches, and
# builds script_compiler into this tools/ folder — after which the editor
# finds it automatically.
#
# Needs: git, a C compiler (macOS: xcode-select --install), internet.
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
SRC="$HERE/StoryTllrC64-src"

if [ ! -d "$SRC" ]; then
  echo "Downloading StoryTllrC64 source..."
  git clone --depth 1 https://github.com/MGProduction/StoryTllrC64.git "$SRC"
fi

echo "Applying required compiler patches..."
sh "$HERE/fix_storytllr_compiler.sh" "$SRC/compiler/main.c"

echo "Building script_compiler..."
sh "$HERE/build_compiler.sh" "$SRC"

echo ""
echo "Done. The editor will find $HERE/script_compiler automatically."
