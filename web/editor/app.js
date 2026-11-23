// The web editor's screens. The game is the same JSON the desktop editor
// opens and saves; every build goes through the desktop's Python (python.js).

import { startPython, buildText, buildGraphical } from "./python.js";

const STORAGE_KEY = "c64-adventure-maker:game";
const DIRECTIONS = ["N", "S", "E", "W"];

const newGame = () => ({
  settings: { title: "New Adventure", author: "", version: "1.0", startroom: 1, maxscore: 100 },
  rooms: { "1": { name: "Start", description: "You are here.", exits: [0, 0, 0, 0], scene_id: null } },
  objects: {},
  vocabulary: { NORTH: ["N"], SOUTH: ["S"], EAST: ["E"], WEST: ["W"] },
  messages: {},
  responses: [],
  scenes: {},
});

let game = newGame();
let selectedRoom = null;
const $ = (id) => document.getElementById(id);

// ------------------------------------------------------------------ data --

/** Fill in anything an older or hand-edited file leaves out, as the desktop does. */
function normalise(data) {
  if (!data || typeof data !== "object" || Array.isArray(data)) {
    throw new Error("that file isn't an adventure (expected a JSON object)");
  }
  const g = data;
  g.settings = g.settings && typeof g.settings === "object" ? g.settings : {};
  for (const key of ["rooms", "objects", "vocabulary", "messages", "scenes"]) {
    if (!g[key] || typeof g[key] !== "object" || Array.isArray(g[key])) g[key] = {};
  }
  if (!Array.isArray(g.responses)) g.responses = [];
  for (const [word, syns] of Object.entries(g.vocabulary)) {
    if (!Array.isArray(syns)) g.vocabulary[word] = [String(syns)];
  }
  for (const room of Object.values(g.rooms)) {
    const exits = Array.isArray(room.exits) ? room.exits : [];
    room.exits = [0, 1, 2, 3].map((i) => Number.parseInt(exits[i], 10) || 0);
    if (room.name === undefined) room.name = "";
    if (room.description === undefined) room.description = "";
    if (room.scene_id === undefined) room.scene_id = null;
  }
  return g;
}

/** Room IDs in the desktop's order: numeric ones by value, others after. */
function roomIds() {
  return Object.keys(game.rooms).sort((a, b) => {
    const na = Number.isInteger(+a) ? +a : 999, nb = Number.isInteger(+b) ? +b : 999;
    return na - nb || a.localeCompare(b);
  });
}

/** A whole number from a text field, or `fallback` while it's mid-edit. */
function intField(text, fallback) {
  const t = String(text).trim();
  return /^-?\d+$/.test(t) ? Number.parseInt(t, 10) : fallback;
}

function slugify(title) {
  return String(title || "game").toLowerCase().replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "") || "game";
}

// --------------------------------------------------------------- storage --

function saveLocally() {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(game));
    $("saved-note").textContent = "Saved in this browser";
  } catch {
    $("saved-note").textContent = "Couldn't save in this browser — use Save to keep your work";
  }
}

let saveTimer = null;
function changed() {
  $("saved-note").textContent = "Saving…";
  clearTimeout(saveTimer);
  saveTimer = setTimeout(saveLocally, 300);
}

function restore() {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored) return normalise(JSON.parse(stored));
  } catch { /* a damaged or blocked store just means a fresh game */ }
  return null;
}

function download(name, bytes, type) {
  const url = URL.createObjectURL(new Blob([bytes], { type }));
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  document.body.append(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

// -------------------------------------------------------------- settings --

const SETTINGS = [
  ["title", "text"], ["author", "text"], ["startroom", "int"],
  ["maxscore", "int"], ["winmessage", "text"],
];

function renderSettings() {
  for (const [key] of SETTINGS) {
    const input = $(`setting-${key}`);
    const value = game.settings[key];
    input.value = value === undefined || value === null ? "" : value;
  }
}

function wireSettings() {
  for (const [key, kind] of SETTINGS) {
    $(`setting-${key}`).addEventListener("input", (e) => {
      game.settings[key] = kind === "int"
        ? intField(e.target.value, game.settings[key] ?? 0)
        : e.target.value;
      changed();
    });
  }
}

// ----------------------------------------------------------------- rooms --

function renderRoomList() {
  const list = $("room-list");
  list.replaceChildren();
  for (const id of roomIds()) {
    const li = document.createElement("li");
    li.setAttribute("role", "option");
    li.dataset.id = id;
    li.tabIndex = -1;
    li.textContent = `${id}: ${game.rooms[id].name}`;
    li.setAttribute("aria-selected", String(id === selectedRoom));
    li.addEventListener("click", () => selectRoom(id));
    list.append(li);
  }
  $("room-count").textContent = `${roomIds().length} rooms`;
}

function selectRoom(id) {
  selectedRoom = id in game.rooms ? id : null;
  renderRoomList();
  renderRoomDetails();
}

function renderRoomDetails() {
  const room = selectedRoom && game.rooms[selectedRoom];
  $("room-details").hidden = !room;
  $("room-empty").hidden = Boolean(room);
  if (!room) return;
  $("room-id").textContent = selectedRoom;
  $("room-name").value = room.name;
  $("room-description").value = room.description;
  DIRECTIONS.forEach((d, i) => { $(`room-exit-${d}`).value = room.exits[i]; });
}

function wireRooms() {
  $("room-name").addEventListener("input", (e) => {
    game.rooms[selectedRoom].name = e.target.value;
    const li = $("room-list").querySelector(`[data-id="${CSS.escape(selectedRoom)}"]`);
    if (li) li.textContent = `${selectedRoom}: ${e.target.value}`;
    changed();
  });
  $("room-description").addEventListener("input", (e) => {
    game.rooms[selectedRoom].description = e.target.value;
    changed();
  });
  DIRECTIONS.forEach((d, i) => {
    $(`room-exit-${d}`).addEventListener("input", (e) => {
      const exits = game.rooms[selectedRoom].exits;
      exits[i] = Math.max(0, intField(e.target.value, exits[i]));
      changed();
    });
  });
  $("room-add").addEventListener("click", () => {
    const numeric = Object.keys(game.rooms).map(Number).filter(Number.isInteger);
    const id = String(numeric.length ? Math.max(...numeric) + 1 : 1);
    game.rooms[id] = { name: `Room ${id}`, description: "", exits: [0, 0, 0, 0], scene_id: null };
    changed();
    selectRoom(id);
    $("room-name").focus();
  });
  $("room-delete").addEventListener("click", () => {
    if (!selectedRoom || !confirm(`Delete room ${selectedRoom}?`)) return;
    delete game.rooms[selectedRoom];
    changed();
    selectRoom(null);
  });
  // Up and down move through the list, as in a desktop list box.
  $("room-list").addEventListener("keydown", (e) => {
    if (e.key !== "ArrowDown" && e.key !== "ArrowUp") return;
    e.preventDefault();
    const ids = roomIds();
    const at = ids.indexOf(selectedRoom);
    const next = ids[Math.min(ids.length - 1, Math.max(0, at + (e.key === "ArrowDown" ? 1 : -1)))];
    if (next) selectRoom(next);
  });
}

// ----------------------------------------------------------------- tabs --

function wireTabs() {
  const tabs = [...document.querySelectorAll('[role="tab"]')];
  for (const tab of tabs) {
    tab.addEventListener("click", () => {
      for (const t of tabs) {
        const on = t === tab;
        t.setAttribute("aria-selected", String(on));
        $(t.getAttribute("aria-controls")).hidden = !on;
      }
    });
  }
}

// ------------------------------------------------------------ open/save --

function loadGame(data, source) {
  game = normalise(data);
  selectedRoom = roomIds()[0] ?? null;
  renderAll();
  saveLocally();
  showResult("info", `Opened ${source}.`);
}

function wireFiles() {
  $("file-new").addEventListener("click", () => {
    if (!confirm("Start a new adventure? Save first if you want to keep this one.")) return;
    loadGame(newGame(), "a new adventure");
  });
  $("file-open").addEventListener("click", () => $("file-input").click());
  $("file-input").addEventListener("change", async (e) => {
    const file = e.target.files[0];
    e.target.value = "";
    if (!file) return;
    try {
      loadGame(JSON.parse(await file.text()), file.name);
    } catch (err) {
      showResult("error", `Couldn't open ${file.name}: ${err.message}`);
    }
  });
  $("file-save").addEventListener("click", () => {
    download(`${slugify(game.settings.title)}.json`,
             JSON.stringify(game, null, 2), "application/json");
  });
}

// ---------------------------------------------------------------- builds --

function showResult(kind, message, notes = []) {
  const box = $("result");
  box.dataset.kind = kind;
  box.replaceChildren();
  const p = document.createElement("p");
  p.textContent = message;
  box.append(p);
  if (notes.length) {
    const ul = document.createElement("ul");
    for (const n of notes) {
      const li = document.createElement("li");
      li.textContent = n;
      ul.append(li);
    }
    box.append(ul);
  }
  box.hidden = false;
}

function wireBuilds() {
  const buttons = [$("build-text"), $("build-graphical")];
  const run = async (label, build, fileName) => {
    buttons.forEach((b) => { b.disabled = true; });
    showResult("info", `Building the ${label} disk…`);
    try {
      const result = await build(game);
      if (!result.ok) {
        showResult("error", `The ${label} disk couldn't be built.`, [result.error]);
        return;
      }
      download(fileName, result.disk, "application/octet-stream");
      showResult("ok", `Your ${label} disk is ready: ${fileName}`, result.notes);
    } catch (err) {
      showResult("error", `The ${label} disk couldn't be built.`, [String(err.message || err)]);
    } finally {
      buttons.forEach((b) => { b.disabled = false; });
    }
  };
  $("build-text").addEventListener("click", () =>
    run("text", buildText, `${slugify(game.settings.title)}-text.d64`));
  $("build-graphical").addEventListener("click", () =>
    run("graphical", buildGraphical, `${slugify(game.settings.title)}.d64`));
}

// ----------------------------------------------------------------- start --

function renderAll() {
  renderSettings();
  renderRoomList();
  renderRoomDetails();
}

function start() {
  wireSettings();
  wireRooms();
  wireTabs();
  wireFiles();
  wireBuilds();
  game = restore() ?? newGame();
  selectedRoom = roomIds()[0] ?? null;
  renderAll();
  // Python loads in the background, so the first build doesn't wait for it.
  startPython((msg) => { $("python-status").textContent = msg; })
    .then(() => { document.body.dataset.python = "ready"; })
    .catch((e) => { $("python-status").textContent = `Python didn't load: ${e.message}`; });
}

start();
