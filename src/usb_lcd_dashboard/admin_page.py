"""The settings editor page.

A single self-contained document: no build step, no CDN, and it works on both
machines with nothing installed. Everything it knows about widgets comes from
/api/widgets, so a newly registered widget appears here with working inputs.
"""

PAGE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>USB LCD Dashboard — settings</title>
<style>
  :root {
    --bg: #081018; --panel: #101c28; --edge: #1d3040;
    --text: #f2f7fb; --muted: #8aa0b2; --accent: #d97757;
    --ok: #2bc48a; --warn: #ffca3a; --err: #ff5f69;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0; background: var(--bg); color: var(--text);
    font: 14px/1.5 "Segoe UI", system-ui, sans-serif;
  }
  header {
    display: flex; align-items: center; gap: 16px; flex-wrap: wrap;
    padding: 14px 20px; border-bottom: 1px solid var(--edge);
    position: sticky; top: 0; background: var(--bg); z-index: 5;
  }
  h1 { font-size: 16px; margin: 0; letter-spacing: .06em; text-transform: uppercase; }
  h2 {
    font-size: 12px; letter-spacing: .1em; text-transform: uppercase;
    color: var(--muted); margin: 0 0 10px;
  }
  .grow { flex: 1; }
  button {
    font: inherit; color: var(--text); background: var(--edge);
    border: 1px solid transparent; border-radius: 7px;
    padding: 7px 13px; cursor: pointer;
  }
  button:hover { border-color: var(--muted); }
  button.primary { background: var(--accent); color: #1a0d07; font-weight: 600; }
  button.danger:hover { border-color: var(--err); color: var(--err); }
  #status { font-size: 13px; min-height: 1.5em; }
  #status.ok { color: var(--ok); } #status.err { color: var(--err); }
  #status.busy { color: var(--muted); }
  main { display: grid; grid-template-columns: 1fr 340px; gap: 20px; padding: 20px; }
  @media (max-width: 900px) { main { grid-template-columns: 1fr; } }
  section { background: var(--panel); border-radius: 12px; padding: 16px; margin-bottom: 20px; }
  #stageWrap { overflow-x: auto; }
  #stage {
    position: relative; background: #050b12; border: 1px solid var(--edge);
    border-radius: 6px; touch-action: none; user-select: none;
  }
  .tile {
    position: absolute; border: 1px solid var(--muted); border-radius: 5px;
    background: rgba(217,119,87,.14); cursor: grab; overflow: hidden;
    display: flex; flex-direction: column; justify-content: center;
    align-items: center; text-align: center; padding: 2px;
  }
  .tile.sel { border-color: var(--accent); background: rgba(217,119,87,.3); z-index: 2; }
  .tile.bad { border-color: var(--err); background: rgba(255,95,105,.25); }
  .tile b { font-size: 12px; pointer-events: none; }
  .tile span { font-size: 10px; color: var(--muted); pointer-events: none; }
  .handle {
    position: absolute; right: 0; bottom: 0; width: 14px; height: 14px;
    background: var(--accent); cursor: nwse-resize; border-radius: 3px 0 4px 0;
  }
  label { display: block; font-size: 12px; color: var(--muted); margin: 9px 0 3px; }
  input, select {
    font: inherit; width: 100%; color: var(--text); background: var(--bg);
    border: 1px solid var(--edge); border-radius: 6px; padding: 6px 8px;
  }
  input[type=checkbox] { width: auto; }
  input:focus, select:focus { outline: none; border-color: var(--accent); }
  .row { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
  .hint { font-size: 11px; color: var(--muted); margin-top: 3px; }
  .check { display: flex; align-items: center; gap: 8px; margin: 10px 0 0; }
  .check label { margin: 0; }
  #preview { width: 100%; display: block; border-radius: 6px; border: 1px solid var(--edge); }
  #warn { color: var(--warn); font-size: 12px; min-height: 1.4em; }
  .ro { font-size: 12px; color: var(--muted); }
  .ro code { color: var(--text); }
  .empty { color: var(--muted); font-size: 13px; }
  .connection { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 10px; }
  .code { font: 600 18px/1.4 ui-monospace, monospace; letter-spacing: .08em; }
</style>
</head>
<body>
<header>
  <h1>USB LCD settings</h1>
  <span class="grow"></span>
  <span id="status"></span>
  <button id="reload">Revert</button>
  <button id="save" class="primary">Save</button>
</header>

<main>
  <div>
    <section>
      <h2>Layout</h2>
      <div id="stageWrap"><div id="stage"></div></div>
      <div id="warn"></div>
      <div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:12px;align-items:center">
        <select id="newWidget" style="width:auto"></select>
        <button id="add">Add tile</button>
        <label style="margin:0 0 0 10px">Snap</label>
        <select id="snap" style="width:auto">
          <option value="1">1 px</option>
          <option value="2">2 px</option>
          <option value="4" selected>4 px</option>
          <option value="12">12 px</option>
        </select>
      </div>
    </section>

    <section>
      <h2>Live panel</h2>
      <img id="preview" alt="the frame currently on the panel">
      <div class="hint" id="previewNote">What the panel is showing now. Saved changes appear within a frame or two.</div>
    </section>
  </div>

  <div>
    <section>
      <h2>Selected tile</h2>
      <div id="tileForm"><p class="empty">Click a tile to edit it.</p></div>
    </section>

    <section>
      <h2>Display</h2>
      <div id="displayForm"></div>
    </section>

    <section>
      <h2>Background</h2>
      <div id="bgForm"></div>
    </section>

    <section>
      <h2>Dashboard</h2>
      <div id="dashForm"></div>
    </section>

    <section>
      <h2>Connections</h2>
      <div id="teamsConnection"><p class="empty">Loading Teams status…</p></div>
    </section>

    <section>
      <h2>Not editable here</h2>
      <div class="ro" id="roInfo"></div>
    </section>
  </div>
</main>

<script>
"use strict";
const $ = (id) => document.getElementById(id);
let cfg = null, widgets = [], sel = -1, dirty = false;
let teams = null;

const STAGE_MAX = 1000;
const scale = () => Math.min(1, STAGE_MAX / Math.max(1, cfg.display.width));
const snap = () => parseInt($("snap").value, 10) || 1;
const spec = (name) => widgets.find((w) => w.name === name);

function setStatus(text, cls) {
  const el = $("status");
  el.textContent = text;
  el.className = cls || "";
}

async function teamsAction(action) {
  setStatus(action === "connect" ? "Starting Teams sign-in…" : "Disconnecting Teams…", "busy");
  const response = await fetch("api/integrations/teams/" + action, {
    method: "POST", headers: {"Content-Type": "application/json"}, body: "{}"
  });
  const body = await response.json();
  if (!response.ok) throw new Error(body.error || "Teams action failed");
  teams = body;
  drawTeams();
  setStatus("", "");
}

function drawTeams() {
  const host = $("teamsConnection");
  if (!host || !teams) return;
  host.innerHTML = "";
  const line = document.createElement("div");
  const status = teams.status || "unknown";
  line.textContent = "Microsoft Teams · " + status + (teams.account ? " · " + teams.account : "");
  host.appendChild(line);
  if (!teams.configured) {
    const hint = document.createElement("div");
    hint.className = "hint";
    hint.textContent = "Set USB_LCD_TEAMS_CLIENT_ID and USB_LCD_TEAMS_TENANT_ID, then restart the dashboard.";
    host.appendChild(hint);
    return;
  }
  if (teams.user_code) {
    const instruction = document.createElement("div");
    instruction.className = "hint";
    instruction.textContent = "Open the Microsoft sign-in page and enter:";
    const code = document.createElement("div");
    code.className = "code"; code.textContent = teams.user_code;
    const link = document.createElement("a");
    link.href = teams.verification_uri; link.target = "_blank"; link.rel = "noopener";
    link.textContent = teams.verification_uri || "Open Microsoft sign-in";
    host.append(instruction, code, link);
  }
  if (teams.error) {
    const error = document.createElement("div");
    error.className = "hint"; error.style.color = "var(--err)"; error.textContent = teams.error;
    host.appendChild(error);
  }
  const actions = document.createElement("div"); actions.className = "connection";
  if (status !== "connecting") {
    const connect = document.createElement("button");
    connect.textContent = status === "connected" ? "Reconnect" : "Connect";
    connect.addEventListener("click", () => teamsAction("connect").catch((e) => setStatus(String(e), "err")));
    actions.appendChild(connect);
  }
  if (status === "connected" || teams.account) {
    const disconnect = document.createElement("button"); disconnect.className = "danger";
    disconnect.textContent = "Disconnect";
    disconnect.addEventListener("click", () => teamsAction("disconnect").catch((e) => setStatus(String(e), "err")));
    actions.appendChild(disconnect);
  }
  host.appendChild(actions);
}

async function refreshTeams() {
  try {
    const response = await fetch("api/integrations/teams");
    teams = await response.json();
    drawTeams();
  } catch (_) { /* The panel editor remains useful if an integration check fails. */ }
}

function markDirty() {
  dirty = true;
  setStatus("Unsaved changes", "busy");
}

// ---------------------------------------------------------------- validation
function overlaps(a, b) {
  return a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h;
}

function problems() {
  const out = [];
  const { width, height } = cfg.display;
  cfg.tiles.forEach((t, i) => {
    if (t.w <= 0 || t.h <= 0) out.push([i, "has no size"]);
    if (t.x < 0 || t.y < 0) out.push([i, "starts off screen"]);
    if (t.x + t.w > width || t.y + t.h > height) out.push([i, "runs off the display"]);
  });
  for (let i = 0; i < cfg.tiles.length; i++)
    for (let j = i + 1; j < cfg.tiles.length; j++)
      if (overlaps(cfg.tiles[i], cfg.tiles[j])) out.push([i, "overlaps tile " + (j + 1)]);
  return out;
}

// -------------------------------------------------------------------- stage
function drawStage() {
  const stage = $("stage"), s = scale();
  stage.style.width = cfg.display.width * s + "px";
  stage.style.height = cfg.display.height * s + "px";
  stage.innerHTML = "";
  const bad = new Set(problems().map(([i]) => i));

  cfg.tiles.forEach((tile, index) => {
    const el = document.createElement("div");
    el.className = "tile" + (index === sel ? " sel" : "") + (bad.has(index) ? " bad" : "");
    el.style.left = tile.x * s + "px";
    el.style.top = tile.y * s + "px";
    el.style.width = tile.w * s + "px";
    el.style.height = tile.h * s + "px";
    el.innerHTML =
      "<b></b><span></span>";
    el.querySelector("b").textContent = tile.widget;
    el.querySelector("span").textContent = tile.w + "x" + tile.h;
    const handle = document.createElement("div");
    handle.className = "handle";
    el.appendChild(handle);
    stage.appendChild(el);

    el.addEventListener("pointerdown", (ev) => {
      const resizing = ev.target === handle;
      // Select by restyling rather than by rebuilding the stage: redrawing here
      // would destroy the very element this gesture is being tracked on.
      sel = index;
      Array.from(stage.children).forEach((node, i) =>
        node.classList.toggle("sel", i === index));
      drawTileForm();
      const start = { px: ev.clientX, py: ev.clientY, ...tile };
      const target = el;
      target.setPointerCapture(ev.pointerId);
      // A click that only selects is not an edit and must not arm the
      // unsaved-changes warning. Pointers emit a move even when they have not
      // travelled, so this tracks the geometry rather than the event.
      let moved = false;
      const move = (m) => {
        const dx = Math.round((m.clientX - start.px) / s);
        const dy = Math.round((m.clientY - start.py) / s);
        const q = (v) => Math.round(v / snap()) * snap();
        if (resizing) {
          tile.w = Math.max(snap(), q(start.w + dx));
          tile.h = Math.max(snap(), q(start.h + dy));
        } else {
          tile.x = Math.max(0, q(start.x + dx));
          tile.y = Math.max(0, q(start.y + dy));
        }
        if (tile.x !== start.x || tile.y !== start.y ||
            tile.w !== start.w || tile.h !== start.h) moved = true;
        target.style.left = tile.x * s + "px";
        target.style.top = tile.y * s + "px";
        target.style.width = tile.w * s + "px";
        target.style.height = tile.h * s + "px";
        target.querySelector("span").textContent = tile.w + "x" + tile.h;
        showWarnings();
        syncTileNumbers();
      };
      const up = () => {
        target.removeEventListener("pointermove", move);
        target.removeEventListener("pointerup", up);
        if (moved) markDirty();
        drawStage();
      };
      target.addEventListener("pointermove", move);
      target.addEventListener("pointerup", up);
      ev.preventDefault();
    });
  });
  showWarnings();
}

function showWarnings() {
  const found = problems();
  $("warn").textContent = found.length
    ? found.map(([i, why]) => "Tile " + (i + 1) + " " + why).join(" · ")
    : "";
}

// -------------------------------------------------------------------- forms
function field(parent, label, value, type, onChange, hint) {
  const wrap = document.createElement("div");
  if (type === "bool") {
    wrap.className = "check";
    const box = document.createElement("input");
    box.type = "checkbox";
    box.checked = !!value;
    box.addEventListener("change", () => { onChange(box.checked); markDirty(); });
    const tag = document.createElement("label");
    tag.textContent = label;
    wrap.append(box, tag);
  } else {
    const tag = document.createElement("label");
    tag.textContent = label;
    const input = document.createElement("input");
    input.type = type === "number" ? "number" : "text";
    if (type === "number") input.step = "any";
    input.value = value === null || value === undefined ? "" : value;
    input.addEventListener("change", () => {
      onChange(type === "number" ? parseFloat(input.value) : input.value);
      markDirty();
    });
    wrap.append(tag, input);
  }
  if (hint) {
    const note = document.createElement("div");
    note.className = "hint";
    note.textContent = hint;
    wrap.appendChild(note);
  }
  parent.appendChild(wrap);
  return wrap;
}

function choice(parent, label, value, options, onChange) {
  const tag = document.createElement("label");
  tag.textContent = label;
  const select = document.createElement("select");
  options.forEach((opt) => {
    const o = document.createElement("option");
    o.value = opt; o.textContent = opt;
    if (opt === value) o.selected = true;
    select.appendChild(o);
  });
  select.addEventListener("change", () => { onChange(select.value); markDirty(); });
  parent.append(tag, select);
  return select;
}

function syncTileNumbers() {
  const tile = cfg.tiles[sel];
  if (!tile) return;
  ["x", "y", "w", "h"].forEach((k) => {
    const el = document.querySelector('[data-rect="' + k + '"]');
    if (el) el.value = tile[k];
  });
}

function drawTileForm() {
  const host = $("tileForm");
  host.innerHTML = "";
  const tile = cfg.tiles[sel];
  if (!tile) {
    host.innerHTML = '<p class="empty">Click a tile to edit it.</p>';
    return;
  }
  choice(host, "Widget", tile.widget, widgets.map((w) => w.name), (v) => {
    tile.widget = v;
    drawStage();
    drawTileForm();
  });
  const info = spec(tile.widget);
  if (info && info.help) {
    const note = document.createElement("div");
    note.className = "hint";
    note.textContent = info.help;
    host.appendChild(note);
  }

  const grid = document.createElement("div");
  grid.className = "row";
  host.appendChild(grid);
  [["x", "X"], ["y", "Y"], ["w", "Width"], ["h", "Height"]].forEach(([key, label]) => {
    const cell = document.createElement("div");
    grid.appendChild(cell);
    const el = field(cell, label, tile[key], "number", (v) => {
      tile[key] = Math.round(v) || 0;
      drawStage();
    });
    el.querySelector("input").dataset.rect = key;
  });

  if (info && info.options.length) {
    const heading = document.createElement("h2");
    heading.textContent = "Options";
    heading.style.marginTop = "18px";
    host.appendChild(heading);
    info.options.forEach((opt) => {
      const present = Object.prototype.hasOwnProperty.call(tile.options, opt.name);
      const value = present ? tile.options[opt.name] : opt.default;
      field(host, opt.name, value, opt.type, (v) => {
        if (v === "" || v === null || (typeof v === "number" && isNaN(v)))
          delete tile.options[opt.name];
        else tile.options[opt.name] = v;
      }, opt.help);
    });
  }

  const remove = document.createElement("button");
  remove.className = "danger";
  remove.textContent = "Delete tile";
  remove.style.marginTop = "16px";
  remove.addEventListener("click", () => {
    cfg.tiles.splice(sel, 1);
    sel = -1;
    markDirty();
    drawStage();
    drawTileForm();
  });
  host.appendChild(remove);
}

function drawSideForms() {
  const d = $("displayForm");
  d.innerHTML = "";
  choice(d, "Kind", cfg.display.kind,
    ["turing_rev_a", "turing_usb", "auto", "simulated", "window"], (v) => { cfg.display.kind = v; });
  field(d, "Device", cfg.display.device, "text", (v) => { cfg.display.device = v; },
    'Serial port, or AUTO');
  const size = document.createElement("div");
  size.className = "row";
  d.appendChild(size);
  const wCell = document.createElement("div"), hCell = document.createElement("div");
  size.append(wCell, hCell);
  field(wCell, "Width", cfg.display.width, "number", (v) => {
    cfg.display.width = Math.round(v) || 1; drawStage();
  });
  field(hCell, "Height", cfg.display.height, "number", (v) => {
    cfg.display.height = Math.round(v) || 1; drawStage();
  });
  choice(d, "Orientation", cfg.display.orientation, ["landscape", "portrait"],
    (v) => { cfg.display.orientation = v; });
  field(d, "Brightness", cfg.display.brightness, "number",
    (v) => { cfg.display.brightness = Math.round(v) || 0; }, "0 to 50");
  field(d, "Refresh (Hz)", cfg.display.refresh_hz, "number",
    (v) => { cfg.display.refresh_hz = v; }, "0.25 to 10");

  const b = $("bgForm");
  b.innerHTML = "";
  const on = document.createElement("div");
  on.className = "check";
  const box = document.createElement("input");
  box.type = "checkbox";
  box.checked = cfg.background !== null;
  const tag = document.createElement("label");
  tag.textContent = "Set a background";
  on.append(box, tag);
  b.appendChild(on);
  box.addEventListener("change", () => {
    cfg.background = box.checked ? { color: "#081018", image: "", fit: "cover" } : null;
    markDirty();
    drawSideForms();
  });
  if (cfg.background) {
    field(b, "Colour", cfg.background.color, "text",
      (v) => { cfg.background.color = v; });
    field(b, "Image", cfg.background.image || "", "text",
      (v) => { cfg.background.image = v; }, "Leave empty for a plain colour");
    choice(b, "Fit", cfg.background.fit, ["cover", "contain", "stretch", "center"],
      (v) => { cfg.background.fit = v; });
  }

  const k = $("dashForm");
  k.innerHTML = "";
  field(k, "Idle title", cfg.dashboard.idle_title, "text",
    (v) => { cfg.dashboard.idle_title = v; });
  field(k, "Switch dwell (s)", cfg.dashboard.switch_dwell_seconds, "number",
    (v) => { cfg.dashboard.switch_dwell_seconds = v; },
    "How long a tile holds a session before it can be taken");
  field(k, "Active TTL (s)", cfg.dashboard.active_ttl_seconds, "number",
    (v) => { cfg.dashboard.active_ttl_seconds = Math.round(v) || 0; });
  field(k, "Approval TTL (s)", cfg.dashboard.approval_ttl_seconds, "number",
    (v) => { cfg.dashboard.approval_ttl_seconds = Math.round(v) || 0; });
  field(k, "Tool TTL (s)", cfg.dashboard.tool_ttl_seconds, "number",
    (v) => { cfg.dashboard.tool_ttl_seconds = Math.round(v) || 0; },
    "Work in flight emits nothing, so it outlives the idle timeout");

  const slots = cfg.tiles.filter((t) => (spec(t.widget) || {}).wants_session).length;
  const ro = cfg.readonly;
  $("roInfo").innerHTML =
    "<p>Agent tiles: <code>" + slots + "</code> — the cap on how many sessions " +
    "show at once.</p><p>IPC: <code>" + ro.ipc_mode + " " + ro.ipc_host + ":" +
    ro.ipc_port + "</code><br>Editor port: <code>" + ro.admin_port + "</code></p>" +
    "<p>Changing the IPC transport would orphan the installed hooks, and changing " +
    "the editor port would cut off this page — edit config.toml for those.</p>";
}

// --------------------------------------------------------------------- data
async function load() {
  setStatus("Loading…", "busy");
  const [c, w] = await Promise.all([
    fetch("api/config").then((r) => r.json()),
    fetch("api/widgets").then((r) => r.json()),
  ]);
  cfg = c;
  widgets = w.widgets;
  sel = -1;
  dirty = false;
  const picker = $("newWidget");
  picker.innerHTML = "";
  widgets.forEach((x) => {
    const o = document.createElement("option");
    o.value = x.name; o.textContent = x.name;
    picker.appendChild(o);
  });
  drawStage();
  drawTileForm();
  drawSideForms();
  setStatus("Loaded", "ok");
}

async function save() {
  const found = problems();
  if (found.length && !confirm("This layout has problems the daemon will reject:\n\n" +
      found.map(([i, why]) => "Tile " + (i + 1) + " " + why).join("\n") +
      "\n\nSend it anyway?")) return;
  setStatus("Saving…", "busy");
  const res = await fetch("api/config", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      display: cfg.display,
      background: cfg.background,
      dashboard: cfg.dashboard,
      tiles: cfg.tiles,
    }),
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    setStatus(body.error || ("save failed: " + res.status), "err");
    return;
  }
  cfg = body.config;
  dirty = false;
  drawStage();
  drawTileForm();
  drawSideForms();
  setStatus("Saved", "ok");
  refreshPreview();
}

function refreshPreview() {
  const img = $("preview");
  img.onerror = () => {
    $("previewNote").textContent =
      "No frame yet — is the daemon running with this config?";
  };
  img.src = "api/preview.png?t=" + Date.now();
}

$("save").addEventListener("click", save);
$("reload").addEventListener("click", () => {
  if (!dirty || confirm("Discard unsaved changes?")) load();
});
$("add").addEventListener("click", () => {
  const name = $("newWidget").value;
  const size = Math.min(cfg.display.height - 24, 300);
  cfg.tiles.push({ widget: name, x: 12, y: 12, w: size, h: Math.max(40, size), options: {} });
  sel = cfg.tiles.length - 1;
  markDirty();
  drawStage();
  drawTileForm();
});
$("snap").addEventListener("change", () => {});
window.addEventListener("beforeunload", (e) => {
  if (dirty) { e.preventDefault(); e.returnValue = ""; }
});

load().then(refreshPreview).catch((err) => setStatus(String(err), "err"));
setInterval(refreshPreview, 2000);
refreshTeams();
setInterval(refreshTeams, 2000);
</script>
</body>
</html>
"""
