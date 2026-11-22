"""One Tk window shared by every GUI test in the run.

On macOS, a second tk.Tk() in the same process never finishes starting:
the first GUI test passed and the second hung for as long as anyone
waited. Linux under Xvfb doesn't do this, which is why CI missed it.

So the window is created once, and each test clears it and builds a
fresh editor inside it. A watchdog turns any future hang into a
failure with a stack trace instead of a silent wait.
"""
import faulthandler
import os
import sys

try:
    import tkinter as tk
except ImportError:          # pragma: no cover
    tk = None

# Generous: a GUI test takes well under a second.
HANG_SECONDS = 60

_root = None


def has_display():
    return bool(os.environ.get("DISPLAY") or sys.platform in ("darwin", "win32"))


def shared_root():
    """The run's one Tk window, created on first use."""
    global _root
    if _root is None:
        _root = tk.Tk()
        _root.withdraw()
    return _root


def _clear(root):
    for after_id in root.tk.splitlist(root.tk.call("after", "info")):
        root.after_cancel(after_id)
    for child in root.winfo_children():
        child.destroy()
    root.config(menu="")


def fresh_editor(ed):
    """Clear the shared window and build a new editor in it."""
    faulthandler.dump_traceback_later(HANG_SECONDS, exit=True)
    root = shared_root()
    _clear(root)
    app = ed.AdventureEditor(root)
    root.update()
    return root, app


def release():
    """Call when a test is done with the editor."""
    faulthandler.cancel_dump_traceback_later()
