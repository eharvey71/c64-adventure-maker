// The editor's Python, running in the page through Pyodide, plus StoryTllr's
// compiler built as WebAssembly. Builds go through the same functions the
// desktop editor uses (build_text_disk, build_graphical_disk), so a disk
// made here is byte-identical to one made there.
//
// Pyodide and the compiler load from pyodide/ and compiler/ next to the
// page; build.sh puts them there.

const REPO_FILES = [
  "adventure_editor_v7.py", "c64build.py",
  "engine/font.png", "engine/stdlib.hjt", "engine/storytllr64.prg",
  "legacy/advplay-c64-current.bas",
];

let ready = null;
let buildCount = 0;

/** Load Python once; later calls return the same promise. */
export function startPython(onStatus = () => {}) {
  if (!ready) {
    ready = load(onStatus).catch((e) => { ready = null; throw e; });
  }
  return ready;
}

async function load(onStatus) {
  onStatus("Loading Python…");
  const py = await loadPyodide({ indexURL: "pyodide/" });
  onStatus("Loading the editor's code…");
  for (const d of ["/repo/engine", "/repo/legacy", "/builds"]) py.FS.mkdirTree(d);
  await Promise.all(REPO_FILES.map(async (f) => {
    const r = await fetch("repo/" + f);
    if (!r.ok) throw new Error(`couldn't load ${f} (${r.status})`);
    py.FS.writeFile("/repo/" + f, new Uint8Array(await r.arrayBuffer()));
  }));
  py.runPython(`
import json, sys
from pathlib import Path
sys.path.insert(0, "/repo")
import adventure_editor_v7 as ed
import c64build
ENGINE = Path("/repo/engine")
RUNTIME = Path("/repo/legacy/advplay-c64-current.bas")
`);
  onStatus("");
  return py;
}

function copyTree(from, to, dir) {
  to.mkdirTree(dir);
  for (const n of from.readdir(dir)) {
    if (n === "." || n === "..") continue;
    const p = dir + "/" + n;
    if (from.isDir(from.stat(p).mode)) copyTree(from, to, p);
    else to.writeFile(p, from.readFile(p));
  }
}

/** Run a build script that leaves {"ok", ...} JSON and maybe a disk file. */
function finish(py, resultJson, diskPath) {
  const result = JSON.parse(resultJson);
  if (result.ok) result.disk = py.FS.readFile(diskPath);
  return result;
}

/**
 * The text disk: the BASIC player and the game.
 * Returns {ok, disk, notes} or {ok: false, error}.
 */
export async function buildText(game) {
  const py = await startPython();
  const disk = `/builds/text-${++buildCount}.d64`;
  py.globals.set("game_json", JSON.stringify(game));
  py.globals.set("disk_path", disk);
  return finish(py, py.runPython(`
game = json.loads(game_json)
notes = [ed.capacity_text(k, n, limit)
         for k, (n, limit) in ed.basic_capacity(game).items() if n > limit]
try:
    built = ed.build_text_disk(game, RUNTIME.read_text())
    Path(disk_path).write_bytes(built["disk"])
    out = {"ok": True, "notes": notes}
except (c64build.BasicError, c64build.DiskError) as e:
    out = {"ok": False, "error": str(e)}
json.dumps(out)
`), disk);
}

/**
 * The graphical disk: StoryTllr's player, the compiled game and room images.
 * Returns {ok, disk, notes} or {ok: false, error}.
 */
export async function buildGraphical(game) {
  const py = await startPython();
  // A fresh compiler for every build: it keeps global state.
  const output = [];
  const C = await createCompiler({
    print: (l) => output.push(l), printErr: (l) => output.push(l),
  });
  globalThis.compileWithWasm = (projDir, script) => {
    copyTree(py.FS, C.FS, projDir);
    C.FS.chdir(projDir);
    C.ccall("compile_game", "number", ["string", "string", "string"],
            [script, "tmp.h", "advcartridge"]);
    copyTree(C.FS, py.FS, projDir);
    return output.join("\n");
  };
  const n = ++buildCount;
  const disk = `/builds/graphical-${n}.d64`;
  py.globals.set("game_json", JSON.stringify(game));
  py.globals.set("proj_dir", `/builds/graphical-${n}`);
  py.globals.set("disk_path", disk);
  return finish(py, py.runPython(`
from js import compileWithWasm
game = json.loads(game_json)
try:
    conv = ed.Converter(game, crop_offset=ed.STORYTLLR_CROP_OFFSET)
    image = ed.build_graphical_disk(
        game, proj_dir, compileWithWasm, ENGINE / "stdlib.hjt",
        (ENGINE / "storytllr64.prg").read_bytes(),
        font_png=ENGINE / "font.png", conv=conv)
    Path(disk_path).write_bytes(image)
    out = {"ok": True,
           "notes": list(dict.fromkeys(conv.warnings + conv.notes))}
except ed.CompileError as e:
    out = {"ok": False,
           "error": "The game didn't compile:\\n" + "\\n".join(e.errors[:12])}
except (c64build.DiskError, ValueError, KeyError) as e:
    out = {"ok": False, "error": str(e)}
json.dumps(out)
`), disk);
}
