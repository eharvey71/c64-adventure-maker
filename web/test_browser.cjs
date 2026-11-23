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

const t0 = Date.now();
const stage = (m) => console.log(`[${((Date.now() - t0) / 1000).toFixed(1)}s] ${m}`);

async function main() {
  fs.copyFileSync(game, path.join(DIST, "test_game.json"));
  await new Promise((r) => server.listen(0, "127.0.0.1", r));
  const port = server.address().port;
  let browser;
  try {
    // The desktop editor's disks first, so a problem there can't be
    // mistaken for one in the browser.
    stage("building the desktop reference disks");
    const python = process.env.PYTHON || "python3";
    const want = JSON.parse(execFileSync(python, [path.join(WEB, "reference.py"), game],
                                         { timeout: 120000, stdio: ["ignore", "pipe", "inherit"] }).toString());
    stage("starting Chromium");
    browser = await chromium.launch();
    const page = await browser.newPage();
    page.on("pageerror", (e) => console.error("page error:", e.message));
    page.on("console", (m) => stage((m.type() === "error" ? "console error: " : "") + m.text()));
    stage("loading the page");
    await page.goto(`http://127.0.0.1:${port}/index.html?game=test_game.json`);
    await page.waitForFunction(() => window.result, null, { timeout: 180000 });
    const got = await page.evaluate(() => window.result);
    if (got.error) throw new Error("in the page: " + got.error);

    console.log(`Chromium ${browser.version()}, in-browser build took ${got.seconds}s`);
    let ok = true;
    for (const k of ["text", "graphical"]) {
      const same = got[k] === want[k];
      ok = ok && same;
      console.log(`${k.padEnd(9)} ${same ? "IDENTICAL" : "DIFFERENT"}  browser ${got[k].slice(0, 16)}  desktop ${want[k].slice(0, 16)}`);
    }
    return ok ? 0 : 1;
  } finally {
    if (browser) await browser.close();
    server.closeAllConnections();
    server.close();
  }
}

// Always exit: anything left open (the server, a browser that failed to
// start) would otherwise keep Node running with no output.
main().then((code) => process.exit(code),
            (e) => { console.error(e); process.exit(1); });
