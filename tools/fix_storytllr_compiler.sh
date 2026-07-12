#!/bin/sh
# fix_storytllr_compiler.sh — required source patches for the StoryTllrC64
# script_compiler (compiler/main.c), verified against repo HEAD (2026-07).
#
# Patch 1: shortdict split byte.
#   When the whole common-word dictionary is < 256 bytes, shortdict[1]
#   stays 0 and the C64 player adds 256 to every dictionary offset,
#   rendering every dictionary word as garbage. Emit 255 = "no split".
#   (Same fix as fix_shortdict_split.sh.)
#
# Patch 2: disable bufferedimgs_start().
#   In current HEAD the image writer buffers all packed room images into
#   memory (imgrooms) whose only consumer, bufferedimgs_end(), is commented
#   out — so img/roomNN files are NEVER written. Disabling the buffering
#   makes IMG_write take its direct file-output path. Regenerated img files
#   are byte-identical to the committed known-good ones in samples/accuse.
#
# Patch 3: disable the "all cells identical" shortcut in IMG_write.
#   For images where an entire screen or color plane is one repeated byte
#   (flat/placeholder art), the writer emits a (count,1,byte) shortcut that
#   the C64 player has NO decoder for: the player misreads the screen plane
#   and reads `count` raw color bytes when only 1 was written, spraying
#   stale cache into color RAM and overrunning into the text rows -> the
#   bottom-of-image garbage that changes as you move between rooms.
#   Real artwork never has a perfectly uniform plane, which is why the
#   shipped samples don't show it. Forcing the normal paths (emit_window
#   for screen, raw nibble-packed color) is fully player-compatible;
#   verified by decoding every packed plane with the player's own hunpack
#   and comparing against the compiler's pre-pack ground truth.
#
# Also note (no patch needed, just knowledge):
#   * script_compiler exits 1 on SUCCESS and 0 when errors occurred.
#   * The compiler only auto-creates tmp/ — img/ must exist beforehand.
#   * Variable names in if: expressions must be PURE LETTERS (the ifget
#     tokenizer stops at digits/underscores).
#   * Globally declared objects may be forward-referenced; room-nested
#     objects may not.

set -e
MAIN="${1:-compiler/main.c}"

if grep -q 'shortdict\[1\] = 255' "$MAIN"; then
  echo "patch 1 (shortdict): already applied"
else
  perl -0pi -e 's/(       shortdict\[2\+i\]=\(pj-bpj\);\n)(       emitattrBYTE\(hf,"shortdict")/$1       if (shortdict[1] == 0)\n        shortdict[1] = 255; \/* no split: whole dict < 256 bytes *\/\n$2/' "$MAIN"
  grep -q 'shortdict\[1\] = 255' "$MAIN" && echo "patch 1 (shortdict): applied" || { echo "patch 1 FAILED"; exit 1; }
fi

if grep -q '^   /\* bufferedimgs_start(); \*/' "$MAIN"; then
  echo "patch 2 (bufferedimgs): already applied"
else
  perl -0pi -e 's/^   bufferedimgs_start\(\);$/   \/* bufferedimgs_start(); *\/ \/* disabled: consumer bufferedimgs_end() is dead code; buffering prevents img\/roomNN output *\//m' "$MAIN"
  grep -q 'disabled: consumer bufferedimgs_end' "$MAIN" && echo "patch 2 (bufferedimgs): applied" || { echo "patch 2 FAILED"; exit 1; }
fi

if grep -q 'all-same shortcut disabled' "$MAIN"; then
  echo "patch 3 (all-same shortcut): already applied"
else
  perl -pi -e 's/^      if\(n==pos\)$/      if(0)\/*all-same shortcut disabled: player has no decoder for it*\//' "$MAIN"
  N=$(grep -c 'all-same shortcut disabled' "$MAIN")
  [ "$N" = "2" ] && echo "patch 3 (all-same shortcut): applied (both sites)" || { echo "patch 3 FAILED (found $N of 2 sites)"; exit 1; }
fi

echo "done."
