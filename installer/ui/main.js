const { invoke } = window.__TAURI__.core;
const { listen } = window.__TAURI__.event;
const $ = (id) => document.getElementById(id);
const log = (line) => { $("log").textContent += line + "\n"; $("log").scrollTop = 1e9; };

// ---- friendly UI state -------------------------------------------------
let installing = false;   // an install is in progress
let forceSetup = false;   // user asked to reinstall / pick another folder
const STEPS = { "Installing Python": "python", "Creating environment": "env", "Installing YSocial": "app" };
const ORDER = ["python", "env", "app"];

const show = (name) => {
  for (const v of ["setup", "installing", "ready"]) $("v-" + v).classList.toggle("on", v === name);
};
const setError = (msg) => { const e = $("err"); e.textContent = msg || ""; e.classList.toggle("on", !!msg); };
const busy = (btn, on) => { btn.classList.toggle("loading", on); btn.disabled = on; };
const friendly = (err) => {
  const m = String(err);
  if (/ENOSPC|No space/i.test(m)) return "There is not enough free disk space. Free some space and try again.";
  if (/network|resolve|connect|timed out|dns/i.test(m)) return "Could not download what is needed. Check your internet connection and try again.";
  if (/EADDRINUSE|address already in use|port/i.test(m)) return "That port is already in use. Pick another one under More options.";
  return "Something went wrong: " + m + " (see Technical details below).";
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
  const home = $("home").value;
  const o = readOptions();
  const installed = await invoke("is_installed", { home });
  if (!installed || forceSetup) { show("setup"); return; }
  const running = await invoke("is_running", { home, host: o.host, port: o.port });
  $("where").textContent = home;
  $("launch").disabled = running;
  $("stop").disabled = !running;
  $("status").className = "yl-status" + (running ? " on" : "");
  $("status").textContent = running ? "Running at http://" + o.host + ":" + o.port : "Stopped";
  $("launch-t").textContent = running ? "YSocial is running" : "Start YSocial";
  $("ready-title").textContent = running ? "YSocial is running" : "Ready when you are";
  $("ready-sub").textContent = running ? "Close this window any time; YSocial keeps running until you stop it."
                                       : "YSocial is installed. Start it whenever you like.";
  show("ready");
}

async function init() {
  $("home").value = await invoke("default_home");
  await loadOptions();
  await listen("progress", (e) => {
    log(e.payload);
    if (e.payload.startsWith("== ")) {
      const label = e.payload.slice(3);
      if (label === "Done") finishSteps(); else markStep(label);
    }
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
    $("launch-t").textContent = "Starting… this can take a minute";
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
