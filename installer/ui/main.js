const { invoke } = window.__TAURI__.core;
const { listen } = window.__TAURI__.event;
const $ = (id) => document.getElementById(id);
const I = (k, fb, v) => window.LAUNCHER_I18N.t(k, fb, v);
const log = (line) => console.log(line);  // raw output goes to <data folder>/logs, not to the UI

// ---- friendly UI state -------------------------------------------------
let installing = false;   // an install is in progress
let confirmingUninstall = false; // uninstall confirmation is open
let forceSetup = false;   // user asked to reinstall / pick another folder
let addingTox = false;
let models = null;        // existing toxicity models: { path, bytes }
let info = { version: null, toxicity: false };  // installed YSocial (read after install/update, not polled)
let latest = null;                               // newer release found on GitHub, if any
let updating = false;

const parseVer = (v) => String(v).replace(/^v/i, "").split("-")[0].split(".").map((x) => parseInt(x, 10) || 0);
const isNewer = (a, b) => {
  const x = parseVer(a), y = parseVer(b);
  for (let i = 0; i < Math.max(x.length, y.length); i++) {
    if ((x[i] || 0) !== (y[i] || 0)) return (x[i] || 0) > (y[i] || 0);
  }
  return false;
};
async function readInstalled() {
  try {
    const raw = await invoke("installed_info", { home: $("home").value });
    if (raw) { const [v, tox] = raw.split(" "); info = { version: v, toxicity: tox === "1" }; return; }
  } catch (_) {}
  info = { version: null, toxicity: false };
}
async function readModels() {
  models = null;
  try {
    const raw = await invoke("toxicity_models", { home: $("home").value });
    if (raw) { const [path, bytes] = raw.split("\t"); models = { path, bytes: Number(bytes) || 0 };
               $("um-path").textContent = path; $("um-size").textContent = fmtSize(models.bytes); }
  } catch (_) {}
}
async function checkForUpdate() {
  latest = null;
  if (!$("checkupdates").checked || !info.version) return;
  try {
    const rel = JSON.parse(await invoke("fetch_latest_release"));
    if (rel.draft || rel.prerelease || !rel.tag_name || !isNewer(rel.tag_name, info.version)) return;
    const assets = rel.assets || [];
    const wheel = assets.find((a) => /^ysocial-.*\.whl$/.test(a.name));
    const cons = assets.find((a) => a.name === "constraints.txt");
    if (!wheel || !cons) return;  // not updatable in place
    latest = {
      version: rel.tag_name.replace(/^v/i, ""), wheel: wheel.browser_download_url, constraints: cons.browser_download_url,
      installer: assets.some((a) => /\.(dmg|msi|exe|AppImage|deb)$/i.test(a.name)), page: rel.html_url,
    };
  } catch (_) { /* offline or rate-limited: stay silent */ }
}
const STEPS = { "Installing Python": "python", "Creating environment": "env", "Installing YSocial": "app" };
const ORDER = ["python", "env", "app"];
const fmtSize = (b) => (b >= 1e9 ? (b / 1e9).toFixed(1) + " GB" : Math.max(1, Math.round(b / 1e6)) + " MB");

const show = (name) => {
  for (const v of ["setup", "installing", "ready", "uninstall"]) $("v-" + v).classList.toggle("on", v === name);
  $("advanced").hidden = name !== "ready";   // start-up options only make sense once installed
};
const setError = (msg) => { const e = $("err"); e.textContent = msg || ""; e.classList.toggle("on", !!msg); };
const busy = (btn, on) => { btn.classList.toggle("loading", on); btn.disabled = on; };
const friendly = (err) => {
  const m = String(err);
  // A failed step carries the last lines of the tool's own output after the first line:
  // show them as they are, the generic patterns below would misread words such as "port".
  if (m.includes("\n") && !/ENOSPC|No space|EADDRINUSE|address already in use/i.test(m)) return I("err.other", "Something went wrong: {msg}", { msg: m });
  if (/ENOSPC|No space/i.test(m)) return I("err.space","There is not enough free disk space. Free some space and try again.");
  if (/network|resolve|connect|timed out|dns/i.test(m)) return I("err.net","Could not download what is needed. Check your internet connection and try again.");
  if (/not started by this installer/i.test(m)) return I("err.foreign","YSocial is already running, but it was not started by this launcher (for example from a terminal). Close that terminal window or end that process, then try again.");
  if (/EADDRINUSE|address already in use|port/i.test(m)) return I("err.port","That port is already in use. Pick another one under More options.");
  return I("err.other", "Something went wrong: {msg}", { msg: m });
};
function markStep(label) {
  const key = STEPS[label];
  if (!key) return;
  const at = ORDER.indexOf(key);
  document.querySelectorAll(".yl-steps li").forEach((li) => {
    const i = ORDER.indexOf(li.dataset.step);
    li.classList.toggle("done", i < at);
    li.classList.toggle("active", i === at);
  });
  $("bar").style.width = Math.round(((at + 0.5) / ORDER.length) * 100) + "%";
}
function finishSteps() {
  document.querySelectorAll(".yl-steps li").forEach((li) => { li.classList.remove("active"); li.classList.add("done"); });
  $("bar").style.width = "100%";
}

// UI field -> setting key (persisted in <data folder>/launcher.json)
const FIELDS = {
  host: "host", port: "port", jupyter: "jupyter", appwindow: "app_window", threaded: "threaded", checkupdates: "check_updates",
};

function readOptions() {
  const o = {
    host: $("host").value.trim() || "127.0.0.1",
    port: parseInt($("port").value, 10) || 8080,
    jupyter: $("jupyter").checked,
    no_notebook: !$("jupyter").checked,   // Jupyter is off unless asked for
    app_window: $("appwindow").checked,
    threaded: $("threaded").checked,
    check_updates: $("checkupdates").checked,
  };
  return o;
}

function applyOptions(o) {
  for (const [id, key] of Object.entries(FIELDS)) {
    if (!(key in o)) continue;
    const el = $(id);
    if (el.type === "checkbox") el.checked = !!o[key]; else el.value = o[key];
  }
}

async function saveOptions() {
  try { await invoke("save_settings", { home: $("home").value, json: JSON.stringify(readOptions()) }); }
  catch (_) { /* settings are a convenience */ }
}

async function loadOptions() {
  try {
    const raw = await invoke("load_settings", { home: $("home").value });
    if (raw) applyOptions(JSON.parse(raw));
  } catch (_) { /* keep defaults */ }
}

async function refresh() {
  if (installing || updating || addingTox) { show("installing"); return; }
  if (confirmingUninstall) { show("uninstall"); return; }
  const home = $("home").value;
  const o = readOptions();
  const installed = await invoke("is_installed", { home });
  if (!installed || forceSetup) { show("setup"); return; }
  const running = await invoke("is_running", { home, host: o.host, port: o.port });
  $("where").textContent = home;
  $("ver").textContent = info.version || "?";
  const showUpd = !!latest && !running;
  $("upd").hidden = !showUpd;
  if (showUpd) {
    $("upd-t").textContent = I("upd.avail", "YSocial {v} is available", { v: latest.version });
    $("upd-launcher").hidden = !latest.installer;
    $("upd-launcher").dataset.href = latest.page;
  }
  $("tox-add").hidden = info.toxicity || running;
  $("launch").disabled = running;
  $("stop").disabled = !running;
  $("status").className = "yl-status" + (running ? " on" : "");
  $("status").textContent = running ? I("status.running", "Running at http://{host}:{port}", { host: o.host, port: o.port }) : I("status.stopped", "Stopped");
  $("launch-t").textContent = running ? I("btn.running", "YSocial is running") : I("btn.start", "Start YSocial");
  $("ready-title").textContent = running ? I("ready.title.run", "YSocial is running") : I("ready.title", "Ready when you are");
  $("ready-sub").textContent = running ? I("ready.sub.run", "Close this window any time; YSocial keeps running until you stop it.")
                                       : I("ready.sub", "YSocial is installed. Start it whenever you like.");
  show("ready");
}

async function init() {
  const L = window.LAUNCHER_I18N;
  $("lang").value = L.saved();
  L.apply();
  $("lang").addEventListener("change", async () => { L.set($("lang").value); await refresh(); });
  $("home").value = await invoke("default_home");
  $("threaded").checked = /Windows/i.test(navigator.userAgent);   // default: on for Windows only
  await loadOptions();
  await listen("progress", (e) => {
    log(e.payload);
    if (e.payload.startsWith("== ")) {
      const label = e.payload.slice(3);
      if (label === "Done") finishSteps();
      else if (label === "Downloading update") $("bar").style.width = "35%";
      else if (label === "Updating YSocial" || label === "Installing toxicity detection") $("bar").style.width = "70%";
      else markStep(label);
    }
  });
  $("uninstall").addEventListener("click", async () => { setError(""); confirmingUninstall = true; $("deletedata").checked = false; $("deletemodels").checked = false;
    await readModels(); $("um-wrap").hidden = !models; await refresh(); });
  $("cancel-uninstall").addEventListener("click", async () => { confirmingUninstall = false; await refresh(); });
  $("confirm-uninstall").addEventListener("click", async () => {
    const o = readOptions();
    busy($("confirm-uninstall"), true);
    $("cancel-uninstall").disabled = true;
    try {
      await invoke("uninstall", { home: $("home").value, host: o.host, port: o.port, deleteData: $("deletedata").checked, deleteModels: $("deletemodels").checked });
      await readInstalled(); models = null;
      forceSetup = false;
    } catch (err) { log("ERROR: " + err); setError(friendly(err)); }
    busy($("confirm-uninstall"), false);
    $("cancel-uninstall").disabled = false;
    confirmingUninstall = false;
    await refresh();
  });
  $("reinstall").addEventListener("click", async () => { forceSetup = true; setError(""); await refresh(); });
  $("home").addEventListener("change", async () => { forceSetup = false; await loadOptions(); await readInstalled(); await refresh(); });
  $("doupdate").addEventListener("click", async () => {
    if (!latest) return;
    setError("");
    updating = true;
    $("v-installing").dataset.mode = "update";
    $("inst-sub").textContent = I("upd.sub", "Updating YSocial. Your data is not touched.");
    $("inst-title").textContent = I("upd.title", "Updating YSocial…");
    $("bar").style.width = "10%";
    show("installing");
    const o = readOptions();
    try {
      await invoke("update", { home: $("home").value, host: o.host, port: o.port, wheelUrl: latest.wheel,
                               constraintsUrl: latest.constraints, toxicity: info.toxicity });
      await readInstalled();   // the new version number is shown right away
      latest = null;
      setError("");
      $("upd-done").textContent = I("upd.done", "Updated to version {v}", { v: info.version });
      $("upd-done").hidden = false;
      setTimeout(() => { $("upd-done").hidden = true; }, 15000);
    } catch (err) { log("ERROR: " + err); setError(friendly(err)); }
    delete $("v-installing").dataset.mode;
    $("inst-title").textContent = I("inst.title", "Setting things up…");
    $("inst-sub").textContent = I("inst.sub", "This takes a few minutes the first time. You can leave this window open.");
    updating = false;
    await refresh();
  });
  document.querySelectorAll("#advanced input, #advanced select, #appwindow").forEach((el) =>
    el.addEventListener("change", async () => { await saveOptions(); await refresh(); }));
  $("addtox").addEventListener("click", async () => {
    setError("");
    addingTox = true;
    $("v-installing").dataset.mode = "update";
    $("inst-title").textContent = I("tox.adding", "Adding toxicity detection…");
    $("inst-sub").textContent = I("tox.adding.sub", "Large download: this can take several minutes.");
    $("bar").style.width = "30%";
    show("installing");
    try {
      await invoke("install_toxicity", { home: $("home").value });
      await readInstalled();
    } catch (err) { log("ERROR: " + err); setError(friendly(err)); }
    delete $("v-installing").dataset.mode;
    $("inst-title").textContent = I("inst.title", "Setting things up…");
    $("inst-sub").textContent = I("inst.sub", "This takes a few minutes the first time. You can leave this window open.");
    addingTox = false;
    await refresh();
  });
  document.addEventListener("click", (e) => {
    const a = e.target.closest && e.target.closest("a[data-ext]");
    if (!a) return;
    e.preventDefault();
    invoke("open_url", { url: a.dataset.href || a.getAttribute("href") }).catch(() => {});
  });
  $("install").addEventListener("click", async () => {
    setError("");
    installing = true;
    markStep("Installing Python");
    show("installing");
    try {
      await invoke("install", { home: $("home").value, toxicity: info.toxicity });
      forceSetup = false;
      await saveOptions();
      await readInstalled();
      checkForUpdate().then(refresh);
    } catch (err) { log("ERROR: " + err); setError(friendly(err)); }
    installing = false;
    await refresh();
  });
  $("launch").addEventListener("click", async () => {
    setError("");
    busy($("launch"), true);
    $("launch-t").textContent = I("btn.starting", "Starting… this can take a minute");
    await saveOptions();
    try { log("Opened " + (await invoke("launch", { home: $("home").value, opts: readOptions() }))); }
    catch (err) { log("ERROR: " + err); setError(friendly(err)); }
    busy($("launch"), false);
    await refresh();
  });
  $("stop").addEventListener("click", async () => {
    $("stop").disabled = true;
    setError("");
    const o = readOptions();
    try { await invoke("stop", { home: $("home").value, host: o.host, port: o.port }); }
    catch (err) { log("ERROR: " + err); setError(friendly(err)); }
    await refresh();
  });
  setInterval(() => { if (!$("launch").classList.contains("loading")) refresh(); }, 3000);
  try { $("launcher-ver").textContent = await invoke("app_version"); } catch (_) {}
  await readInstalled();
  await refresh();
  checkForUpdate().then(refresh);
}
init();
