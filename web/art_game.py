"""Write the sample castle with full-size Koala art on every room.

The art is random but seeded, so it's the same every run. It exercises the
image path - large room images spread across the disk - which the sample
castle's placeholder images don't.

    python3 web/art_game.py out.json
"""
import base64
import json
import random
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def main(out):
    game = json.loads((REPO / "example_castle.json").read_text())
    rng = random.Random(7)
    game["scenes"] = {}
    for rid in game["rooms"]:
        sid = f"S{rid}"
        koala = bytes([0x00, 0x60]) + bytes(rng.randrange(256) for _ in range(10001))
        game["scenes"][sid] = {"name": sid,
                               "koala_b64": base64.b64encode(koala).decode(),
                               "crop_offset": rng.choice([0, 48, 104])}
        game["rooms"][rid]["scene_id"] = sid
    Path(out).write_text(json.dumps(game))


if __name__ == "__main__":
    main(sys.argv[1])
