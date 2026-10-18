const { invoke } = window.__TAURI__.core;
const { listen } = window.__TAURI__.event;
const $ = (id) => document.getElementById(id);
const log = (line) => { $("log").textContent += line + "\n"; $("log").scrollTop = 1e9; };

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
  const home = $("home").value;
  const o = readOptions();
  const installed = await invoke("is_installed", { home });
  const running = installed && (await invoke("is_running", { home, host: o.host, port: o.port }));
  $("launch").disabled = !installed || running;
  $("stop").disabled = !running;
}

async function init() {
  $("home").value = await invoke("default_home");
  await loadOptions();
  await listen("progress", (e) => log(e.payload));
  $("home").addEventListener("change", async () => { await loadOptions(); await refresh(); });
  document.querySelectorAll("#advanced input, #advanced select, #appwindow").forEach((el) =>
    el.addEventListener("change", async () => { await saveOptions(); await refresh(); }));
  $("install").addEventListener("click", async () => {
    $("install").disabled = true;
    try {
      await invoke("install", { home: $("home").value, toxicity: $("toxicity").checked });
    } catch (err) { log("ERROR: " + err); }
    $("install").disabled = false;
    await refresh();
  });
  $("launch").addEventListener("click", async () => {
    $("launch").disabled = true;
    await saveOptions();
    try { log("Opened " + (await invoke("launch", { home: $("home").value, opts: readOptions() }))); }
    catch (err) { log("ERROR: " + err); }
    await refresh();
  });
  $("stop").addEventListener("click", async () => {
    $("stop").disabled = true;
    const o = readOptions();
    try { await invoke("stop", { home: $("home").value, host: o.host, port: o.port }); }
    catch (err) { log("ERROR: " + err); }
    await refresh();
  });
  setInterval(refresh, 3000);
  await refresh();
}
init();
