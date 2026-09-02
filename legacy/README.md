# Legacy — the original text-only era

This folder is reserved for the project's first-generation files: the C64
BASIC runtime and its tooling. **They are not committed yet** — the list
below is the intended contents, not the current contents.

Until they land here, `docs/MANUAL-BUILDS.md` section B (the text-only
build) needs you to supply your own copy of the BASIC runtime. The
editor's **File → Export .adv** still produces the game file it expects.

Files that belong here:

- `advplay-c64-v3.bas`   the BASIC adventure runtime (current)
- `advplay-c64-current.bas` / earlier runtime versions
- `castle-c64.adv`       the sample game in .adv text format
- `fix-lf.py`            line-ending fixer for .adv files
- `build-d64.sh`         the original manual disk build script
- `adventure_editor_v3.py` / `_v5.py`   earlier editor versions

To import them, copy the files in and delete this notice.
