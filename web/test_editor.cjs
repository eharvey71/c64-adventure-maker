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
// Opening a file is asynchronous: wait for the page to finish, or give up.
const settled = (promise) => promise.then(() => true, () => false);

// A Koala file with its load address: the same bytes every run.
function koalaFile() {
  const body = Buffer.alloc(10001);
  let x = 7;
  for (let i = 0; i < body.length; i++) { x = (x * 1103515245 + 12345) & 0x7fffffff; body[i] = x >> 16; }
  return { file: Buffer.concat([Buffer.from([0x00, 0x60]), body]), body };
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
    await settled(page.waitForFunction(
      (n) => document.querySelectorAll("#room-list li").length === n, roomCount, { timeout: 10000 }));
    const items = page.locator("#room-list li");
    check(await items.count() === roomCount, `the room list shows all ${roomCount} rooms`);
    check(await items.first().textContent() === `1: ${source.rooms["1"].name}`,
          "rooms are listed as 'ID: NAME'");
    check(await page.inputValue("#setting-title") === source.settings.title, "the title is shown");
    check(await page.inputValue("#room-name") === source.rooms["1"].name, "the first room is open");
    // Every screen is filled in on opening, not just the one in view.
    check(await page.locator("#object-list li").count() === Object.keys(source.objects).length
          && (await page.inputValue("#vocab-text")).startsWith(Object.keys(source.vocabulary)[0] + "=")
          && (await page.inputValue("#resp-text")).split("\n").filter(Boolean).length === source.responses.length,
          "opening a file fills in every screen");
    check((await page.textContent('[data-capacity="objects"]')).startsWith(
            `${Object.keys(source.objects).length} of 30`), "and the counters");
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
    check((await page.textContent('[data-capacity="rooms"]')).startsWith(`${roomCount + 1} of 20 rooms`),
          "the rooms counter follows the edits");

    stage("tabs");
    const tab = (name) => page.click(`[role="tab"][aria-controls="tab-${name}"]`);
    await tab("objects");
    check(await page.isHidden("#tab-rooms") && await page.isVisible("#tab-objects"),
          "a tab shows its own screen and hides the others");

    stage("objects");
    const objIds = Object.keys(source.objects).sort();
    const objects = page.locator("#object-list li");
    check(await objects.count() === objIds.length, `the object list shows all ${objIds.length} objects`);
    check(await objects.first().textContent() === `${objIds[0]}: ${source.objects[objIds[0]].name}`,
          "objects are listed as 'ID: NAME'");
    check(/takeable objects/.test(await page.textContent('[data-capacity="carried"]')),
          "the carried-objects counter is shown");
    await objects.filter({ hasText: "SWORD:" }).click();
    await page.fill("#object-name", "SHINY SWORD");
    check(await objects.filter({ hasText: "SWORD: SHINY SWORD" }).count() === 1,
          "renaming an object updates the list as you type");
    await page.fill("#object-id", "KEY");
    await page.press("#object-id", "Tab");
    check(/already an object called KEY/.test(await page.textContent("#object-id-note"))
          && await page.inputValue("#object-id") === "SWORD",
          "an ID that's taken is refused and put back");
    await page.fill("#object-id", "blade");
    await page.press("#object-id", "Tab");
    check(await page.inputValue("#object-id") === "BLADE", "a new ID is taken, in capitals");
    const usesSword = source.responses.some((r) => /\bSWORD\b/i.test(
      [r.command, r.condition, r.action].join(" ")));
    if (usesSword) {
      check(/still says? SWORD/.test(await page.textContent("#object-id-note")),
            "renaming warns about responses that still use the old ID");
    }
    await page.click("#object-add");
    const newObj = await page.inputValue("#object-id");
    check(/^OBJ\d+$/.test(newObj) && await objects.count() === objIds.length + 1,
          `adding an object gives it a fresh ID (${newObj})`);
    await page.fill("#object-room", "3");
    await page.fill("#object-properties", "TAKEABLE");

    stage("vocabulary and messages");
    await tab("vocabulary");
    const vocab = await page.inputValue("#vocab-text");
    await page.fill("#vocab-text", vocab + "PUSH=PRESS,SHOVE\n");
    await tab("messages");
    const extra = Array.from({ length: 11 }, (_, i) => `NOTE${i}=Message ${i}`).join("\n");
    await page.fill("#messages-text", (await page.inputValue("#messages-text")) + "\n" + extra);
    check(await page.getAttribute('[data-capacity="messages"]', "data-over") === "true",
          "going over the text engine's message limit is flagged");
    if (shots) await page.screenshot({ path: path.join(shots, "editor-messages.png") });
    await tab("objects");
    if (shots) await page.screenshot({ path: path.join(shots, "editor-objects.png") });

    stage("responses");
    await tab("responses");
    const respText = await page.inputValue("#resp-text");
    const gutter = async () => page.$$eval("#resp-gutter span", (els) => els.map((e) => e.textContent));
    // What the desktop says about the same text, with this game's objects.
    const page_game = await page.evaluate(() => localStorage.getItem("c64-adventure-maker:game"));
    const desktop = JSON.parse(execFileSync(python, ["-c", `
import json, sys
sys.path.insert(0, ${JSON.stringify(path.join(WEB, ".."))})
import adventure_editor_v7 as ed
raw, game = json.load(sys.stdin)
marks, body = ed.responses_report(raw, json.loads(game))
print(json.dumps({"marks": marks, "body": body}))`],
      { input: JSON.stringify([respText.replace(/\n+$/, ""), page_game]) }).toString());
    check(JSON.stringify(await gutter()) === JSON.stringify(desktop.marks),
          `each of the ${source.responses.length} responses is marked as the desktop marks it`);
    check(await page.textContent("#resp-report") === desktop.body,
          "the notes match the desktop's");
    await page.fill("#resp-text", respText + "WAVE WAND:AT 1:YOU WAVE IT.:TELEPORT 3\nJUST SOME WORDS\n");
    const marks = await gutter();
    check(marks.at(-2) === "graphics only" && marks.at(-1) === "not a response",
          "new lines are marked as you type", marks.slice(-2).join(" / "));
    check(/TELEPORT/.test(await page.textContent("#resp-report")),
          "the notes explain what the text engine can't do");
    if (shots) await page.screenshot({ path: path.join(shots, "editor-responses.png"), fullPage: true });
    await page.waitForTimeout(600);  // autosave runs after a short pause

    stage("scenes");
    const tmp = fs.mkdtempSync(path.join(require("os").tmpdir(), "editor-test-"));
    const koala = koalaFile();
    fs.writeFileSync(path.join(tmp, "tower.kla"), koala.file);
    fs.writeFileSync(path.join(tmp, "photo.kla"), Buffer.alloc(500));
    await tab("scenes");
    const scenes = page.locator("#scene-list li");
    const sceneCount = Object.keys(source.scenes).length;
    check(await scenes.count() === sceneCount, `the scene list shows all ${sceneCount} scenes`);
    await page.setInputFiles("#scene-file", path.join(tmp, "tower.kla"));
    await settled(page.waitForSelector('#scene-preview[data-state="ready"]', { timeout: 30000 }));
    check(await scenes.count() === sceneCount + 1 && await page.textContent("#scene-id") === "TOWER",
          "importing tower.kla adds scene TOWER");
    // The preview marks the band's edges in pink, as the desktop's does.
    const rowColour = (y) => page.$eval("#scene-preview", (c, y) =>
      Array.from(c.getContext("2d").getImageData(5, y, 1, 1).data.slice(0, 3)).join(","), y);
    check(await rowColour(48) === "255,0,128" && await rowColour(143) === "255,0,128",
          "the preview marks the centred band, rows 48-143");
    await page.$eval("#scene-band", (el) => { el.value = "104"; el.dispatchEvent(new Event("input")); });
    await settled(page.waitForFunction(() =>
      document.getElementById("scene-preview").dataset.state === "ready", null, { timeout: 30000 }));
    check(await page.textContent("#scene-band-label") === "rows 104-199 of 200"
          && await rowColour(104) === "255,0,128" && await rowColour(48) !== "255,0,128",
          "moving the band moves the marked rows");
    if (shots) await page.screenshot({ path: path.join(shots, "editor-scenes.png") });
    await page.setInputFiles("#scene-file", path.join(tmp, "photo.kla"));
    check(await settled(page.waitForSelector('#result[data-kind="error"]', { timeout: 10000 }))
          && await scenes.count() === sceneCount + 1,
          "a file that isn't a Koala image is refused");
    await tab("rooms");
    await items.first().click();
    await page.selectOption("#room-scene", "TOWER");
    await tab("scenes");
    check((await page.textContent("#scene-usage")).startsWith("Used by: 1 ("),
          "the scene says which room uses it");
    await tab("rooms");
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
    check(JSON.stringify(g.settings) === JSON.stringify(source.settings),
          "everything not edited is saved unchanged");
    check(!("SWORD" in g.objects) && g.objects.BLADE.name === "SHINY SWORD"
          && JSON.stringify(Object.keys(g.objects)) === JSON.stringify(
            [...Object.keys(source.objects).map((k) => (k === "SWORD" ? "BLADE" : k)), newObj]),
          "the saved file has the renamed object, in its old place");
    check(JSON.stringify(g.objects[newObj]) === JSON.stringify(
            { name: `Object ${newObj}`, start_room: 3, description: "", properties: "TAKEABLE" }),
          "the saved file has the new object", JSON.stringify(g.objects[newObj]));
    check(JSON.stringify(g.vocabulary) === JSON.stringify(
            { ...source.vocabulary, PUSH: ["PRESS", "SHOVE"] }),
          "the saved vocabulary is the old one plus the new word");
    check(Object.keys(g.messages).length === Object.keys(source.messages).length + 11
          && g.messages.NOTE3 === "Message 3"
          && Object.entries(source.messages).every(([k, v]) => g.messages[k] === v),
          "the saved messages are the old ones plus the new ones");
    check(JSON.stringify(g.responses) === JSON.stringify([...source.responses,
            { command: "WAVE WAND", condition: "AT 1", message: "YOU WAVE IT.", action: "TELEPORT 3" }]),
          "the saved responses are the old ones plus the new one, without the line that isn't a response");
    const tower = g.scenes.TOWER || {};
    check(tower.name === "tower" && tower.crop_offset === 104
          && Buffer.from(tower.koala_b64 || "", "base64").equals(koala.body)
          && g.rooms["1"].scene_id === "TOWER",
          "the saved file has the scene, its band, and the room it's in");

    stage("building the edited game: the same disk as the desktop's");
    const savedPath = path.join(tmp, "edited.json");
    fs.writeFileSync(savedPath, saved.bytes);
    const wantEdited = JSON.parse(execFileSync(python, [path.join(WEB, "reference.py"), savedPath],
                                                { timeout: 120000, stdio: ["ignore", "pipe", "inherit"] }).toString());
    const gfxEdited = await downloadFrom(page, "build-graphical");
    check(sha(gfxEdited.bytes) === wantEdited.graphical,
          "the graphical disk, with the new scene, is byte-identical to the desktop's");
    const textEdited = await downloadFrom(page, "build-text");
    check(sha(textEdited.bytes) === wantEdited.text,
          "so is the text disk, with every edit");

    stage("deleting a scene that's in use");
    await tab("scenes");
    await page.click("#scene-delete");
    await tab("rooms");
    check(await scenes.count() === sceneCount && await page.inputValue("#room-scene") === "",
          "deleting the scene removes it and clears it from its room");

    stage("opening something that isn't a game");
    const bad = path.join(require("os").tmpdir(), "not-a-game.json");
    fs.writeFileSync(bad, "[1, 2, 3]");
    await page.setInputFiles("#file-input", bad);
    check(await settled(page.waitForSelector('#result[data-kind="error"]', { timeout: 10000 })),
          "a bad file is reported, not opened");
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
