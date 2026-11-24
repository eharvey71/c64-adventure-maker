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
let loaded = null;   // the Python instance, once it has finished loading
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

def responses_lines(raw, game_json):
    marks, body = ed.responses_report(raw, json.loads(game_json))
    return json.dumps({"marks": marks, "body": body})

def import_scene(scenes_json, filename, raw):
    game = {"scenes": json.loads(scenes_json)}
    try:
        sid = ed.add_koala_scene(game, filename, raw.to_bytes())
    except ValueError as e:
        return json.dumps({"ok": False, "error": str(e)})
    return json.dumps({"ok": True, "sid": sid, "scene": game["scenes"][sid]})

def scene_preview(koala_b64, crop_offset, out_path):
    import base64
    ppm = ed.koala_to_ppm_bytes(base64.b64decode(koala_b64), 1, 1, crop_offset)
    Path(out_path).write_bytes(ppm[-160 * 200 * 3:])   # the pixels, after the header

def capacity_lines(game_json):
    game = json.loads(game_json)
    return json.dumps({k: {"text": ed.capacity_text(k, n, limit), "over": n > limit}
                       for k, (n, limit) in ed.basic_capacity(game).items()})
`);
  onStatus("");
  loaded = py;
  return py;
}

/**
 * The desktop's counters against the text engine's limits, keyed as in
 * BASIC_LIMITS: {rooms: {text, over}, ...}. Null until Python has loaded.
 */
export function capacity(game) {
  if (!loaded) return null;
  return JSON.parse(loaded.globals.get("capacity_lines")(JSON.stringify(game)));
}

/**
 * The desktop's report on the Responses text: one mark per line and an
 * explanation of what the text engine does differently. Null until loaded.
 */
export function responsesReport(text, game) {
  if (!loaded) return null;
  return JSON.parse(loaded.globals.get("responses_lines")(text, JSON.stringify(game)));
}

/**
 * Turn a Koala file into a scene, as the desktop's import does.
 * Returns {ok, sid, scene} or {ok: false, error}.
 */
export async function importScene(scenes, fileName, bytes) {
  const py = await startPython();
  return JSON.parse(py.globals.get("import_scene")(JSON.stringify(scenes), fileName, bytes));
}

/**
 * A scene as the desktop previews it: 160x200 RGB bytes, with the rows
 * that don't reach the C64 dimmed and the band's edges marked.
 */
export async function scenePreview(koalaB64, cropOffset) {
  const py = await startPython();
  const out = "/builds/preview.rgb";
  py.globals.get("scene_preview")(koalaB64, cropOffset, out);
  return py.FS.readFile(out);
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
