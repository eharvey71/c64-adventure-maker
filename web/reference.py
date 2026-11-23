"""The desktop editor's own disks for a game, as SHA-256 hashes.

Runs the editor's real build functions (_run_text_build and _run_build)
without the GUI. Needs tools/script_compiler (tools/setup_compiler.sh).

    python3 web/reference.py example_castle.json
"""
import hashlib
import json
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

import adventure_editor_v7 as ed  # noqa: E402


class Dialogs:
    """Stand-in for tkinter.messagebox: any error is fatal."""
    def showerror(self, title, msg): sys.exit(f"{title}: {msg}")
    def showinfo(self, title, msg): pass
    def askyesno(self, title, msg): return False


def build(game_path):
    ed.messagebox = Dialogs()
    game = json.loads(Path(game_path).read_text())

    class Editor:
        _int_field = ed.AdventureEditor._int_field
        generate_adv = ed.AdventureEditor.generate_adv
        def _find_x64sc(self): return None
        def _kit_engine_file(self, name):
            p = REPO / "engine" / name
            return p if p.exists() else None
    Editor.game = game

    out = {}
    with tempfile.TemporaryDirectory() as d:
        ed.AdventureEditor._run_text_build(
            Editor(), REPO / "legacy" / ed.AdventureEditor.BASIC_RUNTIME,
            Path(d))
        out["text"] = next(Path(d).rglob("*.d64")).read_bytes()
    with tempfile.TemporaryDirectory() as d:
        conv = ed.Converter(game, crop_offset=ed.STORYTLLR_CROP_OFFSET)
        ed.AdventureEditor._run_build(
            Editor(), conv, str(REPO / "tools" / "script_compiler"), Path(d))
        out["graphical"] = next(Path(d).rglob("*.d64")).read_bytes()
    return {k: hashlib.sha256(v).hexdigest() for k, v in out.items()}


if __name__ == "__main__":
    print(json.dumps(build(sys.argv[1] if len(sys.argv) > 1
                           else REPO / "example_castle.json")))
