#!/usr/bin/env python3
"""Regenerate the converter golden file. Review the diff before committing."""
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
import adventure_editor_v7 as ed  # noqa: E402

with open(REPO / "example_castle.json") as f:
    game = json.load(f)
out = Path(__file__).parent / "golden" / "example_castle.hjt"
out.parent.mkdir(exist_ok=True)
out.write_text(ed.Converter(game, crop_offset=ed.STORYTLLR_CROP_OFFSET).emit())
print(f"wrote {out}")
