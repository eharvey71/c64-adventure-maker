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

# Pinned so the patches below always apply to the source they were written
# against. Bump deliberately, after re-verifying fix_storytllr_compiler.sh.
STORYTLLR_REPO="https://github.com/MGProduction/StoryTllrC64.git"
STORYTLLR_REV="4730a65790e015a4606d8e6d882992e256184300"

if [ ! -d "$SRC" ]; then
  echo "Downloading StoryTllrC64 source (pinned to ${STORYTLLR_REV})..."
  git init -q "$SRC"
  git -C "$SRC" remote add origin "$STORYTLLR_REPO"
  git -C "$SRC" fetch -q --depth 1 origin "$STORYTLLR_REV"
  git -C "$SRC" checkout -q FETCH_HEAD
else
  HAVE="$(git -C "$SRC" rev-parse HEAD 2>/dev/null || echo unknown)"
  if [ "$HAVE" != "$STORYTLLR_REV" ]; then
    echo "Note: $SRC is at $HAVE, not the pinned $STORYTLLR_REV."
    echo "      Delete it and re-run if the patches below fail."
  fi
fi

echo "Applying required compiler patches..."
sh "$HERE/fix_storytllr_compiler.sh" "$SRC/compiler/main.c"

echo "Building script_compiler..."
sh "$HERE/build_compiler.sh" "$SRC"

echo ""
echo "Done. The editor will find $HERE/script_compiler automatically."
