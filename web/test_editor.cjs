// Drives web/dist/editor.html in headless Chromium the way a person would,
// and checks its disks are byte-identical to the desktop editor's
// (web/reference.py).
//
//   bash web/build.sh && node web/test_editor.cjs [game.json] [screenshot-dir]
//
// Needs Playwright with Chromium: npm install --no-save playwright &&
// npx playwright install chromium
const http = require("http");
const fs = require("fs");
const path = require("path");
const crypto = require("crypto");
const { execFileSync } = require("child_process");
const { chromium } = require("playwright");

const WEB = __dirname;
const DIST = path.join(WEB, "dist");
const game = path.resolve(process.argv[2] || path.join(WEB, "..", "example_castle.json"));
const shots = process.argv[3] ? path.resolve(process.argv[3]) : null;
const TYPES = { ".html": "text/html", ".js": "text/javascript", ".mjs": "text/javascript",
                ".css": "text/css", ".wasm": "application/wasm", ".json": "application/json",
                ".zip": "application/zip" };

const server = http.createServer((req, res) => {
  const url = decodeURIComponent(req.url.split("?")[0]);
  const file = path.join(DIST, url === "/" ? "editor.html" : url);
  if (!file.startsWith(DIST) || !fs.existsSync(file) || fs.statSync(file).isDirectory()) {
    res.writeHead(404); res.end(); return;
  }
  res.writeHead(200, { "Content-Type": TYPES[path.extname(file)] || "application/octet-stream" });
  fs.createReadStream(file).pipe(res);
});

const t0 = Date.now();
const stage = (m) => console.log(`[${((Date.now() - t0) / 1000).toFixed(1)}s] ${m}`);
let failures = 0;
function check(ok, what, detail = "") {
  console.log(`${ok ? "ok  " : "FAIL"}  ${what}${ok || !detail ? "" : `  (${detail})`}`);
  if (!ok) failures++;
}
const sha = (buf) => crypto.createHash("sha256").update(buf).digest("hex");

async function downloadFrom(page, buttonId) {
  const [dl] = await Promise.all([page.waitForEvent("download", { timeout: 120000 }),
                                  page.click(`#${buttonId}`)]);
  return { name: dl.suggestedFilename(), bytes: fs.readFileSync(await dl.path()) };
}

async function main() {
  stage("building the desktop reference disks");
  const python = process.env.PYTHON || "python3";
  const want = JSON.parse(execFileSync(python, [path.join(WEB, "reference.py"), game],
                                       { timeout: 120000, stdio: ["ignore", "pipe", "inherit"] }).toString());
  const source = JSON.parse(fs.readFileSync(game, "utf8"));
  const roomCount = Object.keys(source.rooms).length;

  await new Promise((r) => server.listen(0, "127.0.0.1", r));
  const url = `http://127.0.0.1:${server.address().port}/editor.html`;
  let browser;
  try {
    browser = await chromium.launch();
    const context = await browser.newContext({ acceptDownloads: true, viewport: { width: 1280, height: 860 } });
    const page = await context.newPage();
    page.on("pageerror", (e) => { check(false, "no errors in the page", e.message); });
    page.on("dialog", (d) => d.accept());

    stage("opening the editor");
    await page.goto(url);
    await page.waitForSelector('body[data-python="ready"]', { timeout: 180000 });
    check(await page.locator("#room-list li").count() === 1, "a fresh editor starts with one room");

    stage("opening the game file");
    await page.setInputFiles("#file-input", game);
    const items = page.locator("#room-list li");
    check(await items.count() === roomCount, `the room list shows all ${roomCount} rooms`);
    check(await items.first().textContent() === `1: ${source.rooms["1"].name}`,
          "rooms are listed as 'ID: NAME'");
    check(await page.inputValue("#setting-title") === source.settings.title, "the title is shown");
    check(await page.inputValue("#room-name") === source.rooms["1"].name, "the first room is open");
    if (shots) await page.screenshot({ path: path.join(shots, "editor-rooms.png") });

    stage("building the text disk");
    const text = await downloadFrom(page, "build-text");
    check(sha(text.bytes) === want.text, "the text disk is byte-identical to the desktop's",
          `${sha(text.bytes).slice(0, 16)} vs ${want.text.slice(0, 16)}`);
    stage("building the graphical disk");
    const gfx = await downloadFrom(page, "build-graphical");
    check(sha(gfx.bytes) === want.graphical, "the graphical disk is byte-identical to the desktop's",
          `${sha(gfx.bytes).slice(0, 16)} vs ${want.graphical.slice(0, 16)}`);
    if (shots) await page.screenshot({ path: path.join(shots, "editor-built.png") });

    stage("editing");
    await items.nth(1).click();
    await page.fill("#room-name", "RENAMED HALL");
    check((await items.nth(1).textContent()).endsWith(": RENAMED HALL"), "renaming updates the list as you type");
    const exitBefore = await page.inputValue("#room-exit-E");
    await page.fill("#room-exit-E", "E");
    await page.fill("#room-exit-E", exitBefore);
    await page.click("#room-add");
    const newId = String(Math.max(...Object.keys(source.rooms).map(Number)) + 1);
    check(await items.count() === roomCount + 1, "adding a room adds one to the list");
    check(await page.textContent("#room-id") === newId, `the new room gets the next number (${newId})`);
    await page.fill("#room-name", "NEW ROOM");
    await page.fill("#room-exit-N", "2");
    await page.waitForTimeout(600);  // autosave runs after a short pause

    stage("reloading: the work should still be there");
    await page.reload();
    await page.waitForSelector("#room-list li");
    check(await items.count() === roomCount + 1, "a reload keeps the added room");
    check((await items.nth(1).textContent()).endsWith(": RENAMED HALL"), "a reload keeps the rename");

    stage("saving");
    const saved = await downloadFrom(page, "file-save");
    const g = JSON.parse(saved.bytes.toString("utf8"));
    check(saved.name.endsWith(".json"), "Save downloads a .json file", saved.name);
    check(g.rooms["2"].name === "RENAMED HALL", "the saved file has the rename");
    check(JSON.stringify(g.rooms[newId]) === JSON.stringify(
            { name: "NEW ROOM", description: "", exits: [2, 0, 0, 0], scene_id: null }),
          "the saved file has the new room, with its exit", JSON.stringify(g.rooms[newId]));
    check(JSON.stringify(g.rooms["2"].exits) === JSON.stringify(source.rooms["2"].exits),
          "typing a letter into an exit leaves the exit as it was");
    check(JSON.stringify(g.responses) === JSON.stringify(source.responses)
          && JSON.stringify(g.objects) === JSON.stringify(source.objects),
          "everything not edited is saved unchanged");

    stage("opening something that isn't a game");
    const bad = path.join(require("os").tmpdir(), "not-a-game.json");
    fs.writeFileSync(bad, "[1, 2, 3]");
    await page.setInputFiles("#file-input", bad);
    check((await page.getAttribute("#result", "data-kind")) === "error", "a bad file is reported, not opened");
    check(await items.count() === roomCount + 1, "and the current game is kept");
    return failures ? 1 : 0;
  } finally {
    if (browser) await browser.close();
    server.closeAllConnections();
    server.close();
  }
}

main().then((code) => {
  console.log(code ? `${failures} check(s) failed` : "all checks passed");
  process.exit(code);
}, (e) => { console.error(e); process.exit(1); });
