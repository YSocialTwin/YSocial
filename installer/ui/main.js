const { invoke } = window.__TAURI__.core;
const { listen } = window.__TAURI__.event;
const $ = (id) => document.getElementById(id);
const log = (line) => { $("log").textContent += line + "\n"; $("log").scrollTop = 1e9; };

async function refresh() {
  $("launch").disabled = !(await invoke("is_installed", { home: $("home").value }));
}

async function init() {
  $("home").value = await invoke("default_home");
  await listen("progress", (e) => log(e.payload));
  $("home").addEventListener("change", refresh);
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
    try { log("Opened " + (await invoke("launch", { home: $("home").value, port: 8080 }))); }
    catch (err) { log("ERROR: " + err); }
    await refresh();
  });
  await refresh();
}
init();
