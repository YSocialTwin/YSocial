const { invoke } = window.__TAURI__.core;
const { listen } = window.__TAURI__.event;
const $ = (id) => document.getElementById(id);
const log = (line) => { $("log").textContent += line + "\n"; $("log").scrollTop = 1e9; };

const PORT = 8080;

async function refresh() {
  const home = $("home").value;
  const installed = await invoke("is_installed", { home });
  const running = installed && (await invoke("is_running", { home, port: PORT }));
  $("launch").disabled = !installed || running;
  $("stop").disabled = !running;
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
    try { log("Opened " + (await invoke("launch", { home: $("home").value, port: PORT }))); }
    catch (err) { log("ERROR: " + err); }
    await refresh();
  });
  $("stop").addEventListener("click", async () => {
    $("stop").disabled = true;
    try { await invoke("stop", { home: $("home").value, port: PORT }); }
    catch (err) { log("ERROR: " + err); }
    await refresh();
  });
  setInterval(refresh, 3000);
  await refresh();
}
init();
