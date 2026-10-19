const { invoke } = window.__TAURI__.core;
const { listen } = window.__TAURI__.event;
const $ = (id) => document.getElementById(id);
const I = (k, fb, v) => window.LAUNCHER_I18N.t(k, fb, v);
const log = (line) => { $("log").textContent += line + "\n"; $("log").scrollTop = 1e9; };

// ---- friendly UI state -------------------------------------------------
let installing = false;   // an install is in progress
let confirmingUninstall = false; // uninstall confirmation is open
let forceSetup = false;   // user asked to reinstall / pick another folder
const STEPS = { "Installing Python": "python", "Creating environment": "env", "Installing YSocial": "app" };
const ORDER = ["python", "env", "app"];

const show = (name) => {
  for (const v of ["setup", "installing", "ready", "uninstall"]) $("v-" + v).classList.toggle("on", v === name);
};
const setError = (msg) => { const e = $("err"); e.textContent = msg || ""; e.classList.toggle("on", !!msg); };
const busy = (btn, on) => { btn.classList.toggle("loading", on); btn.disabled = on; };
const friendly = (err) => {
  const m = String(err);
  if (/ENOSPC|No space/i.test(m)) return I("err.space","There is not enough free disk space. Free some space and try again.");
  if (/network|resolve|connect|timed out|dns/i.test(m)) return I("err.net","Could not download what is needed. Check your internet connection and try again.");
  if (/EADDRINUSE|address already in use|port/i.test(m)) return I("err.port","That port is already in use. Pick another one under More options.");
  return I("err.other", "Something went wrong: {msg} (see Technical details below).", { msg: m });
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
  host: "host", port: "port", db: "db", llm: "llm_backend", extra: "extra_args",
  debug: "debug", nonotebook: "no_notebook", development: "development", appwindow: "app_window",
};

function readOptions() {
  const o = {
    host: $("host").value.trim() || "127.0.0.1",
    port: parseInt($("port").value, 10) || 8080,
    db: $("db").value,
    llm_backend: $("llm").value.trim(),
    extra_args: $("extra").value.trim(),
    debug: $("debug").checked,
    no_notebook: $("nonotebook").checked,
    development: $("development").checked,
    app_window: $("appwindow").checked,
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
  if (installing) { show("installing"); return; }
  if (confirmingUninstall) { show("uninstall"); return; }
  const home = $("home").value;
  const o = readOptions();
  const installed = await invoke("is_installed", { home });
  if (!installed || forceSetup) { show("setup"); return; }
  const running = await invoke("is_running", { home, host: o.host, port: o.port });
  $("where").textContent = home;
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
  await loadOptions();
  await listen("progress", (e) => {
    log(e.payload);
    if (e.payload.startsWith("== ")) {
      const label = e.payload.slice(3);
      if (label === "Done") finishSteps(); else markStep(label);
    }
  });
  $("uninstall").addEventListener("click", async () => { setError(""); confirmingUninstall = true; $("deletedata").checked = false; await refresh(); });
  $("cancel-uninstall").addEventListener("click", async () => { confirmingUninstall = false; await refresh(); });
  $("confirm-uninstall").addEventListener("click", async () => {
    const o = readOptions();
    busy($("confirm-uninstall"), true);
    $("cancel-uninstall").disabled = true;
    try {
      await invoke("uninstall", { home: $("home").value, host: o.host, port: o.port, deleteData: $("deletedata").checked });
      forceSetup = false;
    } catch (err) { log("ERROR: " + err); setError(friendly(err)); }
    busy($("confirm-uninstall"), false);
    $("cancel-uninstall").disabled = false;
    confirmingUninstall = false;
    await refresh();
  });
  $("reinstall").addEventListener("click", async () => { forceSetup = true; setError(""); await refresh(); });
  $("home").addEventListener("change", async () => { forceSetup = false; await loadOptions(); await refresh(); });
  document.querySelectorAll("#advanced input, #advanced select, #appwindow").forEach((el) =>
    el.addEventListener("change", async () => { await saveOptions(); await refresh(); }));
  $("install").addEventListener("click", async () => {
    setError("");
    installing = true;
    markStep("Installing Python");
    show("installing");
    try {
      await invoke("install", { home: $("home").value, toxicity: $("toxicity").checked });
      forceSetup = false;
      await saveOptions();
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
  await refresh();
}
init();
