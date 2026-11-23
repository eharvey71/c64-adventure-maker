// Runs the Node build of StoryTllr's compiler (web/check_compiler.sh) in a
// project folder: node run_compiler_node.cjs <compiler.js> <dir> <script>
const fs = require("fs"), path = require("path");
const [js, dir, script] = process.argv.slice(2).map((a, i) => (i < 2 ? path.resolve(a) : a));
require(js)({
  // Handing over the bytes avoids older runtimes trying fetch() on a path.
  wasmBinary: fs.readFileSync(js.replace(/\.js$/, ".wasm")),
}).then((C) => {
  process.chdir(dir);
  C.ccall("compile_game", "number", ["string", "string", "string"],
          [script, "tmp.h", "advcartridge"]);
});
