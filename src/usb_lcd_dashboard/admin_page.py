"""The settings editor page.

A single self-contained document: no build step, no CDN, and it works on both
machines with nothing installed. Everything it knows about widgets comes from
/api/widgets, so a newly registered widget appears here with working inputs.

The page is three stacked regions: the tile stage, which is always visible
because every other control is relative to it; a collapsible panel of settings
that belong to the whole screen; and a tabstrip choosing between the live frame
and the selected widget's settings. Blocks that configure a *source* (Discord,
Windows notifications, human todos) live in the widget tab and appear only when
a widget that consumes that source is selected — the `wants_*` flags on
/api/widgets decide, so a new source-backed widget wires itself up.
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
  main { max-width: 1180px; margin: 0 auto; padding: 20px; }
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
  input, select, textarea {
    font: inherit; width: 100%; color: var(--text); background: var(--bg);
    border: 1px solid var(--edge); border-radius: 6px; padding: 6px 8px;
  }
  input[type=checkbox] { width: auto; }
  textarea { resize: vertical; min-height: 58px; }
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
  .todo { border-top: 1px solid var(--edge); padding: 10px 0; }
  .todo:first-child { border-top: 0; }
  .todo.done input { color: var(--muted); text-decoration: line-through; }
  .todo-actions { display:flex; gap:6px; flex-wrap:wrap; margin-top:7px; }

  /* Collapsible screen-wide settings. <details> does the work; no JS state. */
  details.panel { background: var(--panel); border-radius: 12px; margin-bottom: 20px; }
  details.panel > summary, details.sub > summary {
    cursor: pointer; list-style: none; color: var(--muted);
    font-size: 12px; letter-spacing: .1em; text-transform: uppercase;
  }
  details.panel > summary::-webkit-details-marker,
  details.sub > summary::-webkit-details-marker { display: none; }
  details.panel > summary::before, details.sub > summary::before {
    content: "\25B8"; display: inline-block; width: 14px;
    transition: transform .12s ease;
  }
  details.panel[open] > summary::before, details.sub[open] > summary::before {
    transform: rotate(90deg);
  }
  details.panel[open] > summary, details.sub[open] > summary { color: var(--text); }
  details.panel > summary { padding: 15px 16px; }
  .panel-body {
    padding: 0 16px 6px;
    display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
    gap: 0 22px; align-items: start;
  }
  details.sub > summary { padding: 11px 0; border-top: 1px solid var(--edge); }
  .sub-body { padding-bottom: 14px; }

  /* Tabstrip: live frame vs the selected widget's settings. */
  .tabs { display: flex; gap: 4px; border-bottom: 1px solid var(--edge); margin-bottom: 20px; }
  .tab {
    background: transparent; border: 1px solid transparent; border-bottom-width: 2px;
    border-radius: 8px 8px 0 0; padding: 9px 16px; color: var(--muted);
    font-size: 12px; letter-spacing: .1em; text-transform: uppercase;
  }
  .tab:hover { color: var(--text); border-color: transparent; }
  .tab[aria-selected="true"] {
    color: var(--text); background: var(--panel);
    border-color: transparent; border-bottom-color: var(--accent);
  }
  .editing { font-size: 15px; font-weight: 600; margin: 0 0 2px; }
  .editing span { margin-left: 8px; font-size: 12px; font-weight: 400; color: var(--muted); }

  /* A swatch beside the text box; the text box stays authoritative. The chip
     carries the colour itself and the native picker sits invisibly on top of
     it, because a bare <input type=color> paints as an empty box on some
     renderers — including headless Chromium, where this page is tested. */
  .swatch { display: flex; gap: 8px; align-items: center; }
  .chip {
    position: relative; flex: none; width: 40px; height: 34px;
    border: 1px solid var(--edge); border-radius: 6px; overflow: hidden;
    background-color: transparent;
    background-image:
      linear-gradient(45deg, var(--edge) 25%, transparent 25%, transparent 75%, var(--edge) 75%),
      linear-gradient(45deg, var(--edge) 25%, transparent 25%, transparent 75%, var(--edge) 75%);
    background-size: 12px 12px; background-position: 0 0, 6px 6px;
  }
  .chip input[type=color] {
    position: absolute; inset: 0; width: 100%; height: 100%;
    opacity: 0; padding: 0; border: 0; cursor: pointer;
  }
  .chip.off { opacity: .35; }
  .chip.off input[type=color] { cursor: not-allowed; }
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

  <details class="panel" id="settingsPanel">
    <summary>Settings</summary>
    <div class="panel-body">
      <details class="sub" id="secBackground">
        <summary>Background</summary>
        <div class="sub-body" id="bgForm"></div>
      </details>
      <details class="sub" id="secScreensaver">
        <summary>Screen saver</summary>
        <div class="sub-body" id="screensaverForm"></div>
      </details>
      <details class="sub" id="secDisplay">
        <summary>Display</summary>
        <div class="sub-body">
          <div id="displayForm"></div>
          <div class="connection">
            <button id="reconnectDisplay">Reconnect LCD</button>
            <span class="hint">Reopens the device and repaints the full screen.</span>
          </div>
        </div>
      </details>
    </div>
  </details>

  <div class="tabs" role="tablist">
    <button class="tab" id="tabBtnLive" role="tab"
            aria-selected="true" aria-controls="tabLive">Live panel</button>
    <button class="tab" id="tabBtnWidget" role="tab"
            aria-selected="false" aria-controls="tabWidget">Widget settings</button>
    <button class="tab" id="tabBtnActiveBg" role="tab"
            aria-selected="false" aria-controls="tabActiveBg">Active background</button>
  </div>

  <div id="tabLive" role="tabpanel" aria-labelledby="tabBtnLive">
    <section>
      <img id="preview" alt="the frame currently on the panel">
      <div class="hint" id="previewNote">What the panel is showing now. Saved changes appear within a frame or two.</div>
    </section>
  </div>

  <div id="tabWidget" role="tabpanel" aria-labelledby="tabBtnWidget" hidden>
    <section id="secTile">
      <div id="tileForm"><p class="empty">Click a tile to edit it.</p></div>
    </section>

    <section id="secDash" hidden>
      <h2>Dashboard</h2>
      <div id="dashForm"></div>
    </section>

    <section id="secDiscord" hidden>
      <h2>Discord messages</h2>
      <div id="discordConnection"><p class="empty">Loading Discord status…</p></div>
    </section>

    <section id="secWindows" hidden>
      <h2>Windows notifications</h2>
      <div id="windowsNotifications"><p class="empty">Loading notification access…</p></div>
    </section>

    <section id="secTodos" hidden>
      <h2>Human todos</h2>
      <div id="todoCreate"></div>
      <div class="connection"><button id="todoHistory">Show completed</button></div>
      <div id="todoList"><p class="empty">Loading todos…</p></div>
    </section>

    <section id="secReadonly">
      <h2>Not editable here</h2>
      <div class="ro" id="roInfo"></div>
    </section>
  </div>

  <div id="tabActiveBg" role="tabpanel" aria-labelledby="tabBtnActiveBg" hidden>
    <section>
      <h2>Active background</h2>
      <p class="hint">A red fox that runs across the panel behind every tile.
        It speeds up as the CPU gets busier.</p>
      <div id="activeBgForm"></div>
    </section>
  </div>
</main>

<script>
"use strict";
const $ = (id) => document.getElementById(id);
let cfg = null, widgets = [], sel = -1, dirty = false;
let discord = null;
let windowsNotifications = null;
let todos = [];
let showTodoHistory = false;

const STAGE_MAX = 1000;
const scale = () => Math.min(1, STAGE_MAX / Math.max(1, cfg.display.width));
const snap = () => parseInt($("snap").value, 10) || 1;
const spec = (name) => widgets.find((w) => w.name === name);

// Presentation-only naming. The registry has no label field, and giving it one
// would ripple into every test that pins the /api/widgets shape, so the prettier
// wording lives here and falls back to the raw option name.
const LABELS = {
  hour12: "12-hour clock",
  show_date: "Show the date",
  show_project: "Show the project",
  show_activity: "Show the activity line",
  show_context: "Show the context bar",
  rotation_seconds: "Rotate every (seconds)",
  card_opacity: "Card opacity",
  opacity: "Card opacity",
  background: "Card colour",
  color: "Colour",
  claude_limits: "Claude limits",
};

function humanize(name) {
  const words = String(name).replace(/_/g, " ");
  return words.charAt(0).toUpperCase() + words.slice(1);
}

const labelFor = (name) => LABELS[name] || humanize(name);

// Ranges the loader already enforces, mirrored onto the inputs so the spinner
// steps sensibly and the browser flags a bad value before Save does.
const RANGES = {
  opacity: {min: 0, max: 1, step: 0.05},
  card_opacity: {min: 0, max: 1, step: 0.05},
  rotation_seconds: {min: 1, max: 300, step: 1},
};

function setStatus(text, cls) {
  const el = $("status");
  el.textContent = text;
  el.className = cls || "";
}

function markDirty() {
  dirty = true;
  setStatus("Unsaved changes", "busy");
}

// ---------------------------------------------------------------------- tabs
const TABS = [
  ["live", "tabBtnLive", "tabLive"],
  ["widget", "tabBtnWidget", "tabWidget"],
  ["activeBg", "tabBtnActiveBg", "tabActiveBg"],
];
function showTab(name) {
  for (const [key, btn, panel] of TABS) {
    const on = key === name;
    $(panel).hidden = !on;
    $(btn).setAttribute("aria-selected", String(on));
  }
  // Unhide first: refreshPreview() declines to fetch while the tab is hidden.
  if (name === "live") refreshPreview();
}

const liveTabShowing = () => !$("tabLive").hidden;

async function discordAction(action, payload) {
  setStatus("Updating Discord…", "busy");
  const response = await fetch("api/integrations/discord/" + action, {
    method: "POST", headers: {"Content-Type": "application/json"},
    body: JSON.stringify(payload || {})
  });
  const body = await response.json();
  if (!response.ok) throw new Error(body.error || "Discord action failed");
  discord = body; drawDiscord(); setStatus("Discord updated", "ok");
}

function drawDiscord() {
  const host = $("discordConnection");
  if (!host || !discord || !cfg) return;
  host.innerHTML = "";
  const line = document.createElement("div");
  line.textContent = "Discord · " + (discord.status || "unknown") + (discord.bot ? " · " + discord.bot : "");
  host.appendChild(line);
  if (discord.error) { const e = document.createElement("div"); e.className="hint"; e.style.color="var(--err)"; e.textContent=discord.error; host.appendChild(e); }
  if (!discord.configured) {
    const label = document.createElement("label"); label.textContent = "Bot token";
    const token = document.createElement("input"); token.type="password"; token.autocomplete="off"; token.placeholder="Paste a Discord bot token";
    const save = document.createElement("button"); save.textContent="Save and verify"; save.style.marginTop="8px";
    save.addEventListener("click", () => discordAction("token", {token: token.value}).catch((e) => setStatus(String(e), "err")));
    host.append(label, token, save); return;
  }
  const selected = new Set((cfg.discord || {}).channel_ids || []);
  (discord.channels || []).forEach((channel) => {
    const row=document.createElement("div"); row.className="check";
    const box=document.createElement("input"); box.type="checkbox"; box.checked=selected.has(channel.id);
    box.addEventListener("change", () => { if(box.checked) selected.add(channel.id); else selected.delete(channel.id); cfg.discord={channel_ids:Array.from(selected)}; markDirty(); });
    const label=document.createElement("label"); label.textContent=channel.guild + " / #" + channel.name;
    row.append(box,label); host.appendChild(row);
  });
  if (!(discord.channels || []).length) { const hint=document.createElement("p"); hint.className="empty"; hint.textContent="No readable text channels discovered."; host.appendChild(hint); }
  const actions=document.createElement("div"); actions.className="connection";
  [["channels","Refresh channels"],["clear","Clear new messages"],["disconnect","Disconnect"]].forEach(([action,text]) => {
    const button=document.createElement("button"); button.textContent=text; if(action==="disconnect") button.className="danger";
    button.addEventListener("click", () => discordAction(action, {}).catch((e) => setStatus(String(e), "err"))); actions.appendChild(button);
  });
  host.appendChild(actions);
}

async function refreshDiscord() {
  try { discord = await fetch("api/integrations/discord").then((r) => r.json()); drawDiscord(); }
  catch (_) { /* Settings remain usable if Discord is unavailable. */ }
}

function termList(text) {
  return text.split(",").map((x) => x.trim()).filter((x) => x);
}

function drawWindowsNotifications() {
  const host = $("windowsNotifications");
  if (!host || !windowsNotifications || !cfg) return;
  cfg.windows_notifications ||= {enabled:false, app_ids:[], include_terms:[], exclude_terms:[]};
  const settings = cfg.windows_notifications;
  host.innerHTML = "";
  const line = document.createElement("div");
  line.textContent = "Windows · " + (windowsNotifications.status || "unknown") +
    " · " + (windowsNotifications.matching || 0) + " matching";
  host.appendChild(line);
  if (windowsNotifications.error) {
    const error = document.createElement("div"); error.className="hint";
    error.style.color="var(--err)"; error.textContent=windowsNotifications.error;
    host.appendChild(error);
  }
  if (windowsNotifications.status === "permission_required") {
    const enable = document.createElement("button"); enable.textContent="Enable access";
    enable.style.marginTop="8px";
    enable.addEventListener("click", async () => {
      setStatus("Requesting Windows notification access…", "busy");
      const response = await fetch("api/integrations/windows-notifications/access", {
        method:"POST", headers:{"Content-Type":"application/json"}, body:"{}"
      });
      const body = await response.json();
      if (!response.ok) throw new Error(body.error || "Access request failed");
      setTimeout(refreshWindowsNotifications, 750);
    });
    host.appendChild(enable);
  }
  if (windowsNotifications.status === "denied") {
    const hint=document.createElement("p"); hint.className="hint";
    hint.textContent="Access was denied. Re-enable USB LCD Dashboard under Windows notification privacy settings.";
    host.appendChild(hint);
  }
  const enabledRow=document.createElement("div"); enabledRow.className="check";
  const enabled=document.createElement("input"); enabled.type="checkbox"; enabled.checked=!!settings.enabled;
  enabled.addEventListener("change", () => { settings.enabled=enabled.checked; markDirty(); });
  const enabledLabel=document.createElement("label"); enabledLabel.textContent="Show selected applications";
  enabledRow.append(enabled, enabledLabel); host.appendChild(enabledRow);
  const selected = new Set(settings.app_ids || []);
  (windowsNotifications.apps || []).forEach((app) => {
    const row=document.createElement("div"); row.className="check";
    const box=document.createElement("input"); box.type="checkbox"; box.checked=selected.has(app.id);
    box.addEventListener("change", () => {
      if(box.checked) selected.add(app.id); else selected.delete(app.id);
      settings.app_ids=Array.from(selected); markDirty();
    });
    const label=document.createElement("label"); label.textContent=app.name;
    label.title=app.id; row.append(box,label); host.appendChild(row);
  });
  if (!(windowsNotifications.apps || []).length) {
    const hint=document.createElement("p"); hint.className="empty";
    hint.textContent="Applications appear here after they emit a notification."; host.appendChild(hint);
  }
  field(host, "Include terms", (settings.include_terms || []).join(", "), "text",
    (value) => { settings.include_terms=termList(value); }, "Comma-separated; any term may match");
  field(host, "Exclude terms", (settings.exclude_terms || []).join(", "), "text",
    (value) => { settings.exclude_terms=termList(value); }, "Comma-separated; exclusion wins");
}

async function refreshWindowsNotifications() {
  try {
    windowsNotifications = await fetch("api/integrations/windows-notifications").then((r) => r.json());
    drawWindowsNotifications();
  } catch (_) { /* Settings remain usable if this source is unavailable. */ }
}

// --------------------------------------------------------------- human todos
async function todoRequest(path, method, payload) {
  setStatus("Updating todos…", "busy");
  const response = await fetch("api/todos" + path, {
    method, headers:{"Content-Type":"application/json"},
    body: JSON.stringify(payload || {})
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.error || "Todo action failed");
  await refreshTodos();
  setStatus("Todos updated", "ok");
  return body;
}

function todoFields(host, item, onSave) {
  const title=document.createElement("input"); title.placeholder="What do you need to do?"; title.value=item.title || "";
  const details=document.createElement("textarea"); details.placeholder="Optional details"; details.value=item.details || "";
  const row=document.createElement("div"); row.className="row";
  const priority=document.createElement("select");
  ["urgent","high","normal","low"].forEach((value) => { const o=document.createElement("option"); o.value=value; o.textContent=value; o.selected=(item.priority || "normal")===value; priority.appendChild(o); });
  const due=document.createElement("input"); due.type="date"; due.value=item.due_date || "";
  row.append(priority,due); host.append(title,details,row);
  const save=document.createElement("button"); save.className="primary"; save.textContent=onSave.label;
  save.addEventListener("click", () => onSave.run({title:title.value,details:details.value,priority:priority.value,due_date:due.value || null}).catch((e) => setStatus(String(e),"err")));
  host.appendChild(save);
}

function drawTodoCreate() {
  const host=$("todoCreate"); host.innerHTML="";
  todoFields(host, {priority:"normal"}, {label:"Add todo", run:async (payload) => {
    await todoRequest("", "POST", payload); drawTodoCreate();
  }});
}

function drawTodos() {
  const host=$("todoList"); if(!host) return; host.innerHTML="";
  const visible=todos.filter((item) => showTodoHistory || item.status === "open");
  if(!visible.length) { const p=document.createElement("p"); p.className="empty"; p.textContent=showTodoHistory ? "No todos yet." : "All clear."; host.appendChild(p); return; }
  const open=todos.filter((item) => item.status === "open");
  visible.forEach((item) => {
    const card=document.createElement("div"); card.className="todo" + (item.status === "completed" ? " done" : "");
    todoFields(card,item,{label:"Save",run:(payload)=>todoRequest("/"+item.id,"PATCH",payload)});
    const actions=document.createElement("div"); actions.className="todo-actions";
    const complete=document.createElement("button"); complete.textContent=item.status === "open" ? "Complete" : "Reopen";
    complete.addEventListener("click",()=>todoRequest("/"+item.id+"/"+(item.status === "open" ? "complete" : "reopen"),"POST",{}).catch((e)=>setStatus(String(e),"err")));
    actions.appendChild(complete);
    if(item.status === "open") {
      [["↑",-1],["↓",1]].forEach(([label,delta])=>{ const b=document.createElement("button"); b.textContent=label; b.title=delta<0?"Move up":"Move down";
        b.addEventListener("click",()=>{ const index=open.findIndex((x)=>x.id===item.id), target=index+delta; if(target<0||target>=open.length)return; [open[index],open[target]]=[open[target],open[index]]; todoRequest("/reorder","POST",{ordered_ids:open.map((x)=>x.id)}).catch((e)=>setStatus(String(e),"err")); }); actions.appendChild(b); });
    }
    const remove=document.createElement("button"); remove.className="danger"; remove.textContent="Delete";
    remove.addEventListener("click",()=>{ if(confirm("Permanently delete this todo?")) todoRequest("/"+item.id,"DELETE",{confirm:true}).catch((e)=>setStatus(String(e),"err")); });
    actions.appendChild(remove); card.appendChild(actions); host.appendChild(card);
  });
}

async function refreshTodos() {
  try { const body=await fetch("api/todos?include_completed=1").then((r)=>r.json()); todos=body.todos || []; drawTodos(); }
  catch (_) { /* The layout editor remains usable if todo storage is unavailable. */ }
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
      // Picking a tile is the way into its settings, so go there. The stage sits
      // above the tabstrip and is unaffected by the swap.
      showTab("widget");
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
function field(parent, label, value, type, onChange, hint, attrs) {
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
    if (attrs) Object.keys(attrs).forEach((key) => { input[key] = attrs[key]; });
    if (type === "color") {
      // The swatch is a convenience over the text box, which stays the value of
      // record: "transparent" and "" (meaning "fall back to the widget default")
      // are both legal here and neither can be spelled by <input type=color>.
      const pair = document.createElement("div");
      pair.className = "swatch";
      const chip = document.createElement("span");
      chip.className = "chip";
      const dot = document.createElement("input");
      dot.type = "color";
      chip.appendChild(dot);
      const sync = () => {
        const hex = /^#[0-9a-f]{6}$/i.test(input.value) ? input.value : null;
        dot.value = hex || "#101c28";
        // A named or blank value has no swatch to show, so the chequerboard is
        // left visible; picking one is still allowed so blank can become a
        // colour. A real colour has to cover the chequerboard, which is painted
        // as a background-image and would otherwise sit on top of it.
        chip.style.backgroundColor = hex || "";
        chip.style.backgroundImage = hex ? "none" : "";
        chip.title = hex ? hex : (input.value || "no colour set");
        const named = !hex && input.value !== "";
        dot.disabled = named;
        chip.classList.toggle("off", named);
      };
      dot.addEventListener("input", () => {
        input.value = dot.value;
        onChange(dot.value);
        sync();
        markDirty();
      });
      input.addEventListener("input", sync);
      sync();
      pair.append(chip, input);
      wrap.append(tag, pair);
    } else {
      wrap.append(tag, input);
    }
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

function choice(parent, label, value, options, onChange, textOf) {
  const tag = document.createElement("label");
  tag.textContent = label;
  const select = document.createElement("select");
  options.forEach((opt) => {
    const o = document.createElement("option");
    o.value = opt; o.textContent = textOf ? textOf(opt) : opt;
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
  // Scoped to the form: a second copy of these inputs anywhere on the page would
  // otherwise silently swallow the drag sync.
  const host = $("tileForm");
  ["x", "y", "w", "h"].forEach((k) => {
    const el = host.querySelector('[data-rect="' + k + '"]');
    if (el) el.value = tile[k];
  });
}

// Source-backed blocks belong to the widget that consumes them, so the registry
// flags decide what is on screen rather than a hardcoded list of widget names.
function showContextSections(info) {
  const toggle = (id, wanted) => { $(id).hidden = !wanted; };
  toggle("secDash", !!(info && info.wants_session));
  toggle("secDiscord", !!(info && info.wants_messages));
  toggle("secWindows", !!(info && info.wants_notifications));
  toggle("secTodos", !!(info && info.wants_todos));
}

function drawTileForm() {
  const host = $("tileForm");
  host.innerHTML = "";
  const tile = cfg.tiles[sel];
  if (!tile) {
    host.innerHTML = cfg.tiles.length
      ? '<p class="empty">Click a tile above to edit it.</p>'
      : '<p class="empty">No widgets yet. Pick one above and press Add tile.</p>';
    showContextSections(null);
    drawReadonly();
    return;
  }
  const heading = document.createElement("p");
  heading.className = "editing";
  heading.textContent = labelFor(tile.widget);
  const which = document.createElement("span");
  which.textContent = "tile " + (sel + 1) + " of " + cfg.tiles.length;
  heading.appendChild(which);
  host.appendChild(heading);

  choice(host, "Widget", tile.widget, widgets.map((w) => w.name), (v) => {
    tile.widget = v;
    drawStage();
    drawTileForm();
  }, labelFor);
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
    }, "", {step: 1});
    el.querySelector("input").dataset.rect = key;
  });

  if (info && info.options.length) {
    const title = document.createElement("h2");
    title.textContent = "Options";
    title.style.marginTop = "18px";
    host.appendChild(title);
    info.options.forEach((opt) => {
      const present = Object.prototype.hasOwnProperty.call(tile.options, opt.name);
      const value = present ? tile.options[opt.name] : opt.default;
      field(host, labelFor(opt.name), value, opt.type, (v) => {
        if (v === "" || v === null || (typeof v === "number" && isNaN(v)))
          delete tile.options[opt.name];
        else tile.options[opt.name] = v;
      }, opt.help, RANGES[opt.name]);
    });
  }

  const remove = document.createElement("button");
  remove.className = "danger";
  remove.textContent = "Delete tile";
  remove.style.marginTop = "16px";
  remove.addEventListener("click", () => {
    cfg.tiles.splice(sel, 1);
    sel = Math.min(sel, cfg.tiles.length - 1);
    markDirty();
    drawStage();
    drawTileForm();
  });
  host.appendChild(remove);

  showContextSections(info);
  // The agent-slot count is derived from the tiles, so it goes stale the moment
  // one is added, retyped or deleted.
  drawReadonly();
}

function drawDisplayForm() {
  const d = $("displayForm");
  d.innerHTML = "";
  choice(d, "Kind", cfg.display.kind,
    ["turing_rev_a", "turing_usb", "auto", "simulated", "window"], changeDisplayKind);
  field(d, "Device", cfg.display.device, "text", (v) => { cfg.display.device = v; },
    'Serial port, or AUTO');
  const size = document.createElement("div");
  size.className = "row";
  d.appendChild(size);
  const wCell = document.createElement("div"), hCell = document.createElement("div");
  size.append(wCell, hCell);
  field(wCell, "Width", cfg.display.width, "number", (v) => {
    cfg.display.width = Math.round(v) || 1; drawStage();
  }, "", {min: 1, max: 4096, step: 1});
  field(hCell, "Height", cfg.display.height, "number", (v) => {
    cfg.display.height = Math.round(v) || 1; drawStage();
  }, "", {min: 1, max: 4096, step: 1});
  choice(d, "Orientation", cfg.display.orientation,
    ["landscape", "portrait", "landscape_flipped", "portrait_flipped"],
    (v) => rotateLayout(v), labelFor);
  field(d, "Brightness", cfg.display.brightness, "number",
    (v) => { cfg.display.brightness = Math.round(v) || 0; }, "0 to 50",
    {min: 0, max: 50, step: 1});
  field(d, "Refresh (Hz)", cfg.display.refresh_hz, "number",
    (v) => { cfg.display.refresh_hz = v; }, "0.25 to 10",
    {min: 0.25, max: 10, step: 0.25});
}

function drawBackgroundForm() {
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
    cfg.background = box.checked ? { color: "#081018", image: "", fit: "cover", card_opacity: 0.82 } : null;
    markDirty();
    drawBackgroundForm();
  });
  if (cfg.background) {
    field(b, "Colour", cfg.background.color, "color",
      (v) => { cfg.background.color = v; });
    field(b, "Image", cfg.background.image || "", "text",
      (v) => { cfg.background.image = v; }, "External path, or upload a managed copy below");
    const upload = document.createElement("input");
    upload.type = "file"; upload.accept = "image/png,image/jpeg,image/webp";
    upload.addEventListener("change", async () => {
      const file = upload.files && upload.files[0];
      if (!file) return;
      setStatus("Uploading background…", "busy");
      try {
        const response = await fetch("api/background-image", {
          method: "POST", headers: {"Content-Type": "application/octet-stream"}, body: file
        });
        const body = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(body.error || "upload failed");
        cfg.background.image = body.image;
        markDirty(); drawBackgroundForm();
        setStatus("Background uploaded; Save to apply", "busy");
      } catch (error) { setStatus(String(error), "err"); }
    });
    b.appendChild(upload);
    if (cfg.background.image) {
      const current = document.createElement("div"); current.className = "hint";
      current.textContent = "Selected: " + cfg.background.image;
      const clear = document.createElement("button"); clear.textContent = "Clear picture";
      clear.style.marginTop = "8px";
      clear.addEventListener("click", () => {
        cfg.background.image = ""; markDirty(); drawBackgroundForm();
      });
      b.append(current, clear);
    }
    choice(b, "Fit", cfg.background.fit, ["cover", "contain", "stretch", "center"],
      (v) => { cfg.background.fit = v; }, labelFor);
    field(b, "Card opacity", cfg.background.card_opacity ?? 0.82, "number",
      (v) => { cfg.background.card_opacity = v; }, "0 to 1; tile-specific opacity wins",
      RANGES.card_opacity);
  }
}

function drawScreensaverForm() {
  const saver = $("screensaverForm");
  saver.innerHTML = "";
  cfg.screensaver ||= {enabled: true, idle_seconds: 600};
  field(saver, "Enabled", cfg.screensaver.enabled, "bool",
    (v) => { cfg.screensaver.enabled = v; });
  field(saver, "Idle delay (minutes)", cfg.screensaver.idle_seconds / 60, "number",
    (v) => { cfg.screensaver.idle_seconds = Math.round(v * 60); },
    "Shows a moving clock on black; new dashboard activity wakes it",
    {min: 1, max: 1440, step: 1});
}

function drawDashForm() {
  const k = $("dashForm");
  k.innerHTML = "";
  field(k, "Idle title", cfg.dashboard.idle_title, "text",
    (v) => { cfg.dashboard.idle_title = v; });
  field(k, "Switch dwell (s)", cfg.dashboard.switch_dwell_seconds, "number",
    (v) => { cfg.dashboard.switch_dwell_seconds = v; },
    "How long a tile holds a session before it can be taken", {min: 0, step: 1});
  field(k, "Active TTL (s)", cfg.dashboard.active_ttl_seconds, "number",
    (v) => { cfg.dashboard.active_ttl_seconds = Math.round(v) || 0; }, "", {min: 0, step: 1});
  field(k, "Approval TTL (s)", cfg.dashboard.approval_ttl_seconds, "number",
    (v) => { cfg.dashboard.approval_ttl_seconds = Math.round(v) || 0; }, "", {min: 0, step: 1});
  field(k, "Tool TTL (s)", cfg.dashboard.tool_ttl_seconds, "number",
    (v) => { cfg.dashboard.tool_ttl_seconds = Math.round(v) || 0; },
    "Work in flight emits nothing, so it outlives the idle timeout", {min: 0, step: 1});
}

function drawReadonly() {
  const slots = cfg.tiles.filter((t) => (spec(t.widget) || {}).wants_session).length;
  const ro = cfg.readonly;
  $("roInfo").innerHTML =
    "<p>Agent tiles: <code>" + slots + "</code> — the cap on how many sessions " +
    "show at once.</p><p>IPC: <code>" + ro.ipc_mode + " " + ro.ipc_host + ":" +
    ro.ipc_port + "</code><br>Editor port: <code>" + ro.admin_port + "</code></p>" +
    "<p>Changing the IPC transport would orphan the installed hooks, and changing " +
    "the editor port would cut off this page — edit config.toml for those.</p>";
}

function drawActiveBgForm() {
  const a = $("activeBgForm");
  a.innerHTML = "";
  const on = document.createElement("div");
  on.className = "check";
  const box = document.createElement("input");
  box.type = "checkbox";
  box.checked = cfg.active_background !== null && cfg.active_background !== undefined;
  const tag = document.createElement("label");
  tag.textContent = "Run the fox";
  on.append(box, tag);
  a.appendChild(on);
  box.addEventListener("change", () => {
    cfg.active_background = box.checked
      ? { enabled: true, scale: 0.45, speed_min: 40, speed_max: 220, opacity: 1 }
      : null;
    markDirty();
    drawActiveBgForm();
  });
  if (cfg.active_background) {
    const ab = cfg.active_background;
    // Presence of the block is the on/off switch, so keep enabled in step.
    ab.enabled = true;
    field(a, "Height (fraction of panel)", ab.scale, "number",
      (v) => { ab.scale = v; }, "0 to 1", {min: 0.05, max: 1, step: 0.05});
    field(a, "Speed at idle CPU (px/s)", ab.speed_min, "number",
      (v) => { ab.speed_min = v; }, "How fast it runs when the CPU is quiet",
      {min: 0, step: 5});
    field(a, "Speed at full CPU (px/s)", ab.speed_max, "number",
      (v) => { ab.speed_max = v; }, "How fast it runs when the CPU is pegged",
      {min: 0, step: 5});
    field(a, "Opacity", ab.opacity, "number",
      (v) => { ab.opacity = v; }, "0 to 1", {min: 0, max: 1, step: 0.05});
    const note = document.createElement("div");
    note.className = "hint";
    note.textContent = "Runs behind the tiles; set a tile's card colour to " +
      "transparent to let more of the fox show through.";
    a.appendChild(note);
  }
}

function drawPanels() {
  drawDisplayForm();
  drawBackgroundForm();
  drawScreensaverForm();
  drawDashForm();
  drawActiveBgForm();
  drawReadonly();
}

function changeDisplayKind(kind) {
  const previous = cfg.display.kind;
  cfg.display.kind = kind;
  // Auto means hardware-selected saved profiles. Preserve the panel currently
  // being edited so the daemon can seed its first profile from this layout.
  if (kind === "auto") {
    drawPanels();
    return;
  }
  if (kind === "turing_usb") {
    // The shipped wide-panel profile is the TURZX 1CBE:0092. Switching only
    // the transport used to retain the Rev A 480x320 canvas, so every reconnect
    // was rejected even though the USB device had been found successfully.
    cfg.display.width = 1920;
    cfg.display.height = 462;
    const legacyProfile = cfg.tiles.length === 1 &&
      cfg.tiles[0].widget === "legacy" && cfg.tiles[0].x === 0 &&
      cfg.tiles[0].y === 0 && cfg.tiles[0].w <= 480 && cfg.tiles[0].h <= 480;
    if (legacyProfile || previous === "turing_rev_a" || previous === "auto") {
      cfg.tiles = [
        {widget:"clock", x:12, y:12, w:404, h:438,
          options:{title:"HOME", hour12:true, seconds:true, show_date:true}},
        {widget:"agent", x:428, y:12, w:486, h:438, options:{}},
        {widget:"messages", x:926, y:12, w:486, h:438,
          options:{title:"DISCORD"}},
        {widget:"crab", x:1424, y:12, w:484, h:438,
          options:{animate:true, alarm:true}}
      ];
      sel = 0;
    }
    drawStage();
    drawTileForm();
    drawPanels();
    return;
  }
  if (kind !== "turing_rev_a") {
    drawPanels();
    return;
  }

  // The serial Rev A panel has one fixed native size. Keeping a wide panel's
  // dimensions and tiles when its transport is changed strands the daemon at
  // connect time, leaving the Rev A panel on its white power-on screen.
  const portrait = cfg.display.orientation === "portrait" ||
    cfg.display.orientation === "portrait_flipped";
  cfg.display.width = portrait ? 320 : 480;
  cfg.display.height = portrait ? 480 : 320;
  cfg.tiles = [{
    widget: "legacy", x: 0, y: 0,
    w: cfg.display.width, h: cfg.display.height, options: {}
  }];
  sel = 0;
  drawStage();
  drawTileForm();
  drawPanels();
}

async function rotateLayout(target) {
  const source = cfg.display.orientation;
  if (target === source) return;
  setStatus("Rotating layout…", "busy");
  try {
    const response = await fetch("api/layout/rotate", {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({source, target, width: cfg.display.width,
        height: cfg.display.height, tiles: cfg.tiles})
    });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(body.error || "rotation failed");
    cfg.display.orientation = target;
    cfg.display.width = body.width; cfg.display.height = body.height;
    cfg.tiles = body.tiles;
    markDirty(); drawStage(); drawTileForm(); drawPanels();
  } catch (error) {
    setStatus(String(error), "err"); drawPanels();
  }
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
  // The widget tab always has something to show when there is anything to show.
  sel = cfg.tiles.length ? 0 : -1;
  dirty = false;
  const picker = $("newWidget");
  picker.innerHTML = "";
  widgets.forEach((x) => {
    const o = document.createElement("option");
    o.value = x.name; o.textContent = labelFor(x.name);
    picker.appendChild(o);
  });
  drawStage();
  drawTileForm();
  drawPanels();
  await refreshDiscord();
  await refreshWindowsNotifications();
  drawTodoCreate();
  await refreshTodos();
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
      active_background: cfg.active_background,
      screensaver: cfg.screensaver,
      dashboard: cfg.dashboard,
      discord: cfg.discord,
      windows_notifications: cfg.windows_notifications,
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
  if (sel >= cfg.tiles.length) sel = cfg.tiles.length - 1;
  drawStage();
  drawTileForm();
  drawPanels();
  setStatus("Saved", "ok");
  refreshPreview();
}

function refreshPreview() {
  // Polling a PNG the user cannot see is pure waste, and the panel is on the
  // other tab most of the time. showTab() re-arms this when it comes back.
  if (document.hidden || !liveTabShowing()) return;
  const img = $("preview");
  img.onerror = () => {
    $("previewNote").textContent =
      "No frame yet — is the daemon running with this config?";
  };
  img.src = "api/preview.png?t=" + Date.now();
}

async function reconnectDisplay() {
  const button = $("reconnectDisplay");
  button.disabled = true;
  setStatus("Requesting LCD reconnect…", "busy");
  try {
    const response = await fetch("api/display/reconnect", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: "{}",
    });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(body.error || "LCD reconnect failed");
    setStatus("LCD reconnect requested", "ok");
    setTimeout(refreshPreview, 2500);
  } catch (error) {
    setStatus(String(error), "err");
  } finally {
    button.disabled = false;
  }
}

$("save").addEventListener("click", save);
$("reconnectDisplay").addEventListener("click", reconnectDisplay);
$("reload").addEventListener("click", () => {
  if (!dirty || confirm("Discard unsaved changes?")) load();
});
$("tabBtnLive").addEventListener("click", () => showTab("live"));
$("tabBtnWidget").addEventListener("click", () => showTab("widget"));
$("tabBtnActiveBg").addEventListener("click", () => showTab("activeBg"));
$("add").addEventListener("click", () => {
  const name = $("newWidget").value;
  const size = Math.min(cfg.display.height - 24, 300);
  cfg.tiles.push({ widget: name, x: 12, y: 12, w: size, h: Math.max(40, size), options: {} });
  sel = cfg.tiles.length - 1;
  markDirty();
  drawStage();
  drawTileForm();
  showTab("widget");
});
$("snap").addEventListener("change", () => {});
$("todoHistory").addEventListener("click", () => {
  showTodoHistory=!showTodoHistory;
  $("todoHistory").textContent=showTodoHistory ? "Hide completed" : "Show completed";
  drawTodos();
});
document.addEventListener("visibilitychange", () => { if (!document.hidden) refreshPreview(); });
window.addEventListener("beforeunload", (e) => {
  if (dirty) { e.preventDefault(); e.returnValue = ""; }
});

load().then(refreshPreview).catch((err) => setStatus(String(err), "err"));
setInterval(refreshPreview, 2000);
setInterval(refreshDiscord, 5000);
setInterval(refreshTodos, 5000);
</script>
</body>
</html>
"""
