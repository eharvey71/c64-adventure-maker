// Runs web/dist/index.html in headless Chromium and checks that the disks it
// builds are byte-identical to the desktop editor's (web/reference.py).
//
//   bash web/build.sh && node web/test_browser.cjs [game.json]
//
// Needs Playwright with Chromium: npm install --no-save playwright &&
// npx playwright install chromium
const http = require("http");
const fs = require("fs");
const path = require("path");
const { execFileSync } = require("child_process");
const { chromium } = require("playwright");

const WEB = __dirname;
const DIST = path.join(WEB, "dist");
const game = path.resolve(process.argv[2] || path.join(WEB, "..", "example_castle.json"));
const TYPES = { ".html": "text/html", ".js": "text/javascript", ".mjs": "text/javascript",
                ".wasm": "application/wasm", ".json": "application/json", ".zip": "application/zip" };

const server = http.createServer((req, res) => {
  const url = decodeURIComponent(req.url.split("?")[0]);
  const file = path.join(DIST, url === "/" ? "index.html" : url);
  if (!file.startsWith(DIST) || !fs.existsSync(file) || fs.statSync(file).isDirectory()) {
    res.writeHead(404); res.end(); return;
  }
  res.writeHead(200, { "Content-Type": TYPES[path.extname(file)] || "application/octet-stream" });
  fs.createReadStream(file).pipe(res);
});

(async () => {
  fs.copyFileSync(game, path.join(DIST, "test_game.json"));
  await new Promise((r) => server.listen(0, "127.0.0.1", r));
  const port = server.address().port;
  const browser = await chromium.launch();
  try {
    const page = await browser.newPage();
    page.on("pageerror", (e) => console.error("page error:", e.message));
    await page.goto(`http://127.0.0.1:${port}/index.html?game=test_game.json`);
    await page.waitForFunction(() => window.result, null, { timeout: 180000 });
    const got = await page.evaluate(() => window.result);
    if (got.error) throw new Error(got.error);

    const python = process.env.PYTHON || "python3";
    const want = JSON.parse(execFileSync(python, [path.join(WEB, "reference.py"), game]).toString());

    console.log(`Chromium ${browser.version()}, in-browser build took ${got.seconds}s`);
    let ok = true;
    for (const k of ["text", "graphical"]) {
      const same = got[k] === want[k];
      ok = ok && same;
      console.log(`${k.padEnd(9)} ${same ? "IDENTICAL" : "DIFFERENT"}  browser ${got[k].slice(0, 16)}  desktop ${want[k].slice(0, 16)}`);
    }
    process.exitCode = ok ? 0 : 1;
  } finally {
    await browser.close();
    server.close();
  }
})().catch((e) => { console.error(e); process.exitCode = 1; });
