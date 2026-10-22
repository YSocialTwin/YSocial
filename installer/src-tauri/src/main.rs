// YSocial graphical installer / launcher (E5 prototype, NOT yet compiled or tested).
//
// Steps mirror scripts/packaging/bootstrap_env.py:
//   1. uv python install 3.12            (managed, isolated interpreter)
//   2. uv venv --seed                    (pip available for plugins)
//   3. uv pip install <wheel>            (+ optional "toxicity" extra)
// Bundled resources (placed by CI in src-tauri/resources/): the `uv` binary and
// the ysocial-*.whl built from the same commit.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::io::{BufRead, BufReader};
use std::net::TcpStream;
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};
use serde::Deserialize;
use tauri::{AppHandle, Emitter, Manager, WebviewUrl, WebviewWindowBuilder};

const PYTHON_VERSION: &str = "3.12";
const TORCH_CPU_INDEX: &str = "https://download.pytorch.org/whl/cpu";

/// Same defaults as y_web/src/system/path_utils.py::_default_home_dir.
fn default_home_path() -> PathBuf {
    if let Ok(v) = std::env::var("YSOCIAL_HOME") {
        if !v.is_empty() {
            return PathBuf::from(v);
        }
    }
    if cfg!(target_os = "macos") {
        PathBuf::from(std::env::var("HOME").unwrap_or_default())
            .join("Library/Application Support/YSocial")
    } else if cfg!(target_os = "windows") {
        PathBuf::from(std::env::var("USERPROFILE").unwrap_or_default())
            .join("AppData/Local/YSocial")
    } else {
        PathBuf::from(std::env::var("HOME").unwrap_or_default()).join(".ysocial")
    }
}

/// Every child process goes through here: on Windows the app has no console, so without
/// CREATE_NO_WINDOW each `curl`, `uv` or `taskkill` would flash a console window.
fn new_cmd<S: AsRef<std::ffi::OsStr>>(program: S) -> Command {
    #[allow(unused_mut)]
    let mut c = Command::new(program);
    // The Linux AppImage runtime exports PYTHONHOME/PYTHONPATH pointing into its own mount
    // (/tmp/.mount_*/usr). Inherited by uv and by YSocial's virtualenv, they make that Python
    // fail at start ("No module named 'encodings'"). Nothing we launch should use them.
    c.env_remove("PYTHONHOME").env_remove("PYTHONPATH");
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        c.creation_flags(0x0800_0000); // CREATE_NO_WINDOW
    }
    c
}

fn venv_python(home: &Path) -> PathBuf {
    let venv = home.join("runtime").join("venv");
    if cfg!(target_os = "windows") {
        venv.join("Scripts").join("python.exe")
    } else {
        venv.join("bin").join("python")
    }
}

fn venv_ysocial(home: &Path) -> PathBuf {
    let venv = home.join("runtime").join("venv");
    if cfg!(target_os = "windows") {
        venv.join("Scripts").join("ysocial.exe")
    } else {
        venv.join("bin").join("ysocial")
    }
}

fn resource_file(app: &AppHandle, name: &str) -> Result<PathBuf, String> {
    let dir = app.path().resource_dir().map_err(|e| e.to_string())?;
    let direct = dir.join("resources").join(name);
    if direct.exists() {
        return Ok(direct);
    }
    let flat = dir.join(name);
    if flat.exists() {
        return Ok(flat);
    }
    Err(format!("bundled resource not found: {name}"))
}

fn find_wheel(app: &AppHandle) -> Result<PathBuf, String> {
    let dir = app.path().resource_dir().map_err(|e| e.to_string())?;
    for base in [dir.join("resources"), dir] {
        if let Ok(entries) = std::fs::read_dir(&base) {
            for e in entries.flatten() {
                let p = e.path();
                if p.extension().map(|x| x == "whl").unwrap_or(false) {
                    return Ok(p);
                }
            }
        }
    }
    Err("bundled ysocial wheel not found".into())
}

fn file_uri(p: &Path) -> String {
    let s = p.to_string_lossy().replace('\\', "/");
    if s.starts_with('/') {
        format!("file://{s}")
    } else {
        format!("file:///{s}")
    }
}

/// Run a command, forwarding every output line to the UI as a `progress` event.
fn run_step(app: &AppHandle, label: &str, cmd: &mut Command) -> Result<(), String> {
    let _ = app.emit("progress", format!("== {label}"));
    let mut child = cmd
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .map_err(|e| format!("{label}: {e}"))?;
    // The last lines of output travel with the error: they hold the real reason (uv, pip,
    // curl...) and the interface otherwise only shows "failed (exit status N)".
    let tail: Arc<Mutex<Vec<String>>> = Arc::new(Mutex::new(Vec::new()));
    let keep = |tail: &Arc<Mutex<Vec<String>>>, line: &str| {
        if let Ok(mut t) = tail.lock() {
            if !line.trim().is_empty() {
                t.push(line.trim_end().to_string());
                if t.len() > 8 {
                    t.remove(0);
                }
            }
        }
    };
    let stderr = child.stderr.take();
    let app2 = app.clone();
    let tail2 = tail.clone();
    let t = std::thread::spawn(move || {
        if let Some(s) = stderr {
            for line in BufReader::new(s).lines().flatten() {
                if let Ok(mut t) = tail2.lock() {
                    if !line.trim().is_empty() {
                        t.push(line.trim_end().to_string());
                        if t.len() > 8 {
                            t.remove(0);
                        }
                    }
                }
                let _ = app2.emit("progress", line);
            }
        }
    });
    if let Some(s) = child.stdout.take() {
        for line in BufReader::new(s).lines().flatten() {
            keep(&tail, &line);
            let _ = app.emit("progress", line);
        }
    }
    let _ = t.join();
    let status = child.wait().map_err(|e| e.to_string())?;
    if status.success() {
        Ok(())
    } else {
        let lines = tail.lock().map(|t| t.join("\n")).unwrap_or_default();
        if lines.is_empty() {
            Err(format!("{label} failed ({status})"))
        } else {
            Err(format!("{label} failed ({status})\n{lines}"))
        }
    }
}

#[tauri::command]
fn default_home() -> String {
    default_home_path().to_string_lossy().into_owned()
}

#[tauri::command]
fn is_installed(home: String) -> bool {
    venv_ysocial(Path::new(&home)).exists()
}

const RELEASES_API: &str = "https://api.github.com/repos/YSocialTwin/YSocial/releases/latest";
const RELEASE_DOWNLOAD_PREFIX: &str = "https://github.com/YSocialTwin/YSocial/releases/download/";

/// Version of the launcher itself (kept equal to YSocial's by CI/tests).
#[tauri::command]
fn app_version(app: AppHandle) -> String {
    app.package_info().version.to_string()
}

/// Installed YSocial version and whether the optional toxicity extra is present.
#[tauri::command]
fn installed_info(home: String) -> Option<String> {
    let py = venv_python(Path::new(&home));
    if !py.exists() {
        return None;
    }
    let code = "import importlib.metadata as m, importlib.util as u; \
                print(m.version('ysocial'), int(u.find_spec('detoxify') is not None))";
    let out = new_cmd(py).args(["-c", code]).stderr(Stdio::null()).output().ok()?;
    if !out.status.success() {
        return None;
    }
    Some(String::from_utf8_lossy(&out.stdout).trim().to_string())
}

/// Latest published GitHub release (JSON text), fetched with curl (present on
/// macOS, Windows 10+ and Linux). Errors are returned so the UI can stay silent.
#[tauri::command]
async fn fetch_latest_release() -> Result<String, String> {
    tauri::async_runtime::spawn_blocking(|| {
        let out = new_cmd("curl")
            .args(["-fsSL", "--max-time", "8", "-H", "Accept: application/vnd.github+json",
                   "-H", "User-Agent: ysocial-launcher", RELEASES_API])
            .output()
            .map_err(|e| e.to_string())?;
        if out.status.success() {
            Ok(String::from_utf8_lossy(&out.stdout).into_owned())
        } else {
            Err("release information not available".into())
        }
    })
    .await
    .map_err(|e| e.to_string())?
}

fn download(app: &AppHandle, url: &str, dest: &Path) -> Result<(), String> {
    if !url.starts_with(RELEASE_DOWNLOAD_PREFIX) {
        return Err("Refusing to download from an unexpected address".into());
    }
    let mut c = new_cmd("curl");
    c.args(["-fL", "--retry", "3", "--max-time", "900", "-o"]).arg(dest).arg(url);
    run_step(app, "Downloading update", &mut c)
}

/// Update an existing installation in place from a release: the data folder is untouched,
/// the environment keeps its optional extras, database migrations run at next start.
#[tauri::command]
async fn update(
    app: AppHandle, home: String, host: String, port: u16,
    wheel_url: String, constraints_url: String, toxicity: bool,
) -> Result<(), String> {
    tauri::async_runtime::spawn_blocking(move || {
        let home = PathBuf::from(&home);
        let runtime = home.join("runtime");
        if !venv_python(&home).exists() {
            return Err("YSocial is not installed in this folder".into());
        }
        let name = wheel_url.rsplit('/').next().unwrap_or("");
        if !name.starts_with("ysocial-") || !name.ends_with(".whl") || name.contains("..") {
            return Err("Unexpected release asset".into());
        }
        stop_service(&app, &home, &host, port, true)?;
        let tmp = runtime.join("update");
        let _ = std::fs::remove_dir_all(&tmp);
        std::fs::create_dir_all(&tmp).map_err(|e| e.to_string())?;
        let wheel = tmp.join(name);
        let constraints = tmp.join("constraints.txt");
        download(&app, &wheel_url, &wheel)?;
        download(&app, &constraints_url, &constraints)?;
        let uv = resource_file(&app, if cfg!(windows) { "uv.exe" } else { "uv" })?;
        let mut c = new_cmd(&uv);
        c.args(["pip", "install", "--upgrade", "--python"]).arg(venv_python(&home));
        c.arg("--constraint").arg(&constraints);
        let target = if toxicity {
            c.args(["--extra-index-url", TORCH_CPU_INDEX, "--index-strategy", "unsafe-best-match"]);
            format!("ysocial[toxicity] @ {}", file_uri(&wheel))
        } else {
            wheel.to_string_lossy().into_owned()
        };
        c.arg(target).env("UV_PYTHON_INSTALL_DIR", runtime.join("python")).env("UV_PYTHON_INSTALL_BIN", "0").env("YSOCIAL_HOME", &home);
        run_step(&app, "Updating YSocial", &mut c)?;
        std::fs::copy(&constraints, runtime.join("constraints.txt")).map_err(|e| e.to_string())?;
        let _ = std::fs::remove_dir_all(&tmp);
        let _ = app.emit("progress", "== Done");
        Ok(())
    })
    .await
    .map_err(|e| e.to_string())?
}

#[tauri::command]
async fn install(app: AppHandle, home: String, toxicity: bool) -> Result<(), String> {
    tauri::async_runtime::spawn_blocking(move || {
        let home = PathBuf::from(&home);
        let runtime = home.join("runtime");
        std::fs::create_dir_all(&runtime).map_err(|e| e.to_string())?;
        let uv = resource_file(&app, if cfg!(windows) { "uv.exe" } else { "uv" })?;
        let wheel = find_wheel(&app)?;
        let venv = runtime.join("venv");
        let py_dir = runtime.join("python");
        let base = |c: &mut Command| {
            // UV_PYTHON_INSTALL_BIN=0: do not also link python3.x into ~/.local/bin. If a file
            // of that name is already there uv fails ("Executable already exists ... not managed
            // by uv", exit 2) and the install stops; YSocial only needs the managed interpreter.
            c.env("UV_PYTHON_INSTALL_DIR", &py_dir).env("UV_PYTHON_INSTALL_BIN", "0").env("YSOCIAL_HOME", &home);
        };

        let mut c = new_cmd(&uv);
        c.args(["python", "install", PYTHON_VERSION]);
        base(&mut c);
        run_step(&app, "Installing Python", &mut c)?;

        // A previous attempt that stopped half way leaves runtime/venv behind, and recent uv
        // refuses to create a venv over an existing directory ("exit status 2" on every retry).
        // The venv holds no user data (experiments live in the data folder), so start clean.
        if venv.exists() {
            let _ = app.emit("progress", "Removing a leftover environment from a previous attempt");
            std::fs::remove_dir_all(&venv).map_err(|e| format!("Cannot remove the old environment: {e}"))?;
        }
        let mut c = new_cmd(&uv);
        c.args(["venv", "--seed", "--python", PYTHON_VERSION]).arg(&venv);
        base(&mut c);
        run_step(&app, "Creating environment", &mut c)?;

        let mut c = new_cmd(&uv);
        c.args(["pip", "install", "--python"]).arg(venv_python(&home));
        // Pinned versions (requirements.lock, bundled as constraints.txt): keep them
        // next to the runtime so plugin installs are constrained to the same pins.
        if let Ok(bundled) = resource_file(&app, "constraints.txt") {
            let target = runtime.join("constraints.txt");
            std::fs::copy(&bundled, &target).map_err(|e| e.to_string())?;
            c.arg("--constraint").arg(&target);
        }
        let target = if toxicity {
            c.args(["--extra-index-url", TORCH_CPU_INDEX, "--index-strategy", "unsafe-best-match"]);
            format!("ysocial[toxicity] @ {}", file_uri(&wheel))
        } else {
            wheel.to_string_lossy().into_owned()
        };
        c.arg(target);
        base(&mut c);
        run_step(&app, "Installing YSocial", &mut c)?;
        let _ = app.emit("progress", "== Done");
        Ok(())
    })
    .await
    .map_err(|e| e.to_string())?
}

fn open_in_browser(url: &str) {
    let _ = if cfg!(target_os = "macos") {
        new_cmd("open").arg(url).spawn()
    } else if cfg!(target_os = "windows") {
        new_cmd("cmd").args(["/C", "start", "", url]).spawn()
    } else {
        new_cmd("xdg-open").arg(url).spawn()
    };
}

fn pid_file(home: &Path) -> PathBuf {
    home.join("ysocial.pid")
}

fn read_pid(home: &Path) -> Option<u32> {
    std::fs::read_to_string(pid_file(home)).ok()?.trim().parse().ok()
}

fn pid_alive(pid: u32) -> bool {
    if cfg!(target_os = "windows") {
        new_cmd("tasklist")
            .args(["/FI", &format!("PID eq {pid}"), "/NH"])
            .output()
            .map(|o| String::from_utf8_lossy(&o.stdout).contains(&pid.to_string()))
            .unwrap_or(false)
    } else {
        new_cmd("kill")
            .args(["-0", &pid.to_string()])
            .stderr(Stdio::null())
            .status()
            .map(|s| s.success())
            .unwrap_or(false)
    }
}

/// Address to probe/open for a bind host (wildcards are reached through loopback).
fn probe_host(host: &str) -> String {
    match host.trim() {
        "" | "0.0.0.0" | "::" | "[::]" => "127.0.0.1".to_string(),
        h => h.to_string(),
    }
}

fn port_open(host: &str, port: u16) -> bool {
    TcpStream::connect((probe_host(host).as_str(), port)).is_ok()
}

#[tauri::command]
fn is_running(home: String, host: String, port: u16) -> bool {
    let home = PathBuf::from(home);
    read_pid(&home).map(pid_alive).unwrap_or(false) || port_open(&host, port)
}

/// All descendants of `root` (children, grandchildren, ...), also those in other
/// sessions/process groups (simulators are started detached). Unix only.
fn descendant_pids(root: u32) -> Vec<u32> {
    let Ok(out) = new_cmd("ps").args(["-A", "-o", "pid=,ppid="]).output() else {
        return Vec::new();
    };
    let table: Vec<(u32, u32)> = String::from_utf8_lossy(&out.stdout)
        .lines()
        .filter_map(|l| {
            let mut it = l.split_whitespace();
            Some((it.next()?.parse().ok()?, it.next()?.parse().ok()?))
        })
        .collect();
    let mut found = vec![root];
    let mut i = 0;
    while i < found.len() {
        let parent = found[i];
        for (pid, ppid) in &table {
            if *ppid == parent && !found.contains(pid) {
                found.push(*pid);
            }
        }
        i += 1;
    }
    found.remove(0);
    found
}

/// Stop YSocial: SIGTERM (clean shutdown: experiments and Jupyter are stopped by
/// YSocial itself), then SIGKILL after 40 s. Windows: taskkill of the process tree.
/// Unix: YSocial runs in its own process group, so leftovers (YServer/YClient,
/// Jupyter) are killed with the group once the main process is gone.
fn stop_service(app: &AppHandle, home: &Path, host: &str, port: u16, close_window: bool) -> Result<(), String> {
    let Some(pid) = read_pid(home) else {
        return if port_open(host, port) {
            Err(format!(
                "Something is listening on port {port}, but it was not started by this installer"
            ))
        } else {
            Ok(())
        };
    };
    let _ = app.emit("progress", format!("Stopping YSocial (pid {pid})..."));
    // Snapshot the descendants now: they are reparented once YSocial exits.
    let descendants = if cfg!(target_os = "windows") { Vec::new() } else { descendant_pids(pid) };
    if cfg!(target_os = "windows") {
        // Ask YSocial to shut down by itself (like SIGTERM elsewhere): it watches for this
        // file and stops its simulators and services. If nobody picks the request up
        // (an older YSocial), fall back to ending the process tree at once.
        let stop_file = home.join("ysocial.stop");
        let acknowledged = std::fs::write(&stop_file, b"stop").is_ok() && {
            let t0 = Instant::now();
            let mut taken = false;
            while t0.elapsed() < Duration::from_secs(6) {
                if !stop_file.exists() || !pid_alive(pid) {
                    taken = true;
                    break;
                }
                std::thread::sleep(Duration::from_millis(250));
            }
            taken
        };
        if !acknowledged {
            let _ = std::fs::remove_file(&stop_file);
            let _ = new_cmd("taskkill").args(["/PID", &pid.to_string(), "/T", "/F"]).status();
        }
    } else {
        let _ = new_cmd("kill").args(["-TERM", &pid.to_string()]).status();
    }
    let start = Instant::now();
    // YSocial stops every simulator (and their Ray helpers) before exiting.
    while start.elapsed() < Duration::from_secs(40) {
        if !pid_alive(pid) {
            break;
        }
        std::thread::sleep(Duration::from_millis(300));
    }
    if pid_alive(pid) {
        let _ = app.emit("progress", "Forcing stop...");
        if cfg!(target_os = "windows") {
            // graceful shutdown did not finish in time: end the whole process tree
            let _ = new_cmd("taskkill").args(["/PID", &pid.to_string(), "/T", "/F"]).status();
        } else {
            let _ = new_cmd("kill").args(["-KILL", &pid.to_string()]).status();
        }
        std::thread::sleep(Duration::from_millis(500));
    }
    if !cfg!(target_os = "windows") {
        // Anything still in the process group (started by YSocial) goes too.
        let _ = new_cmd("kill").args(["-KILL", &format!("-{pid}")]).stderr(Stdio::null()).status();
        // Simulators in their own session (and their helpers) that survived.
        for d in descendants {
            let _ = new_cmd("kill").args(["-KILL", &d.to_string()]).stderr(Stdio::null()).status();
        }
    }
    let _ = std::fs::remove_file(pid_file(home));
    if pid_alive(pid) {
        return Err("Could not stop YSocial".into());
    }
    if close_window {
        if let Some(w) = app.get_webview_window(APP_WINDOW) {
            let _ = w.close();
        }
    }
    let _ = app.emit("progress", "YSocial stopped.");
    Ok(())
}

#[tauri::command]
async fn stop(app: AppHandle, home: String, host: String, port: u16) -> Result<(), String> {
    tauri::async_runtime::spawn_blocking(move || stop_service(&app, Path::new(&home), &host, port, true))
        .await
        .map_err(|e| e.to_string())?
}

fn user_home() -> PathBuf {
    PathBuf::from(std::env::var(if cfg!(windows) { "USERPROFILE" } else { "HOME" }).unwrap_or_default())
}

/// Where YSocial keeps the toxicity models (mirrors y_web/src/system/model_cache.py):
/// $YSOCIAL_MODEL_CACHE_DIR, else `model_cache_dir` in <home>/y_web/system/model_cache_settings.json,
/// else ~/.cache/ysocial_models.
fn models_root(home: &Path) -> PathBuf {
    if let Ok(v) = std::env::var("YSOCIAL_MODEL_CACHE_DIR") {
        if !v.is_empty() {
            return PathBuf::from(v);
        }
    }
    let settings = home.join("y_web").join("system").join("model_cache_settings.json");
    if let Ok(text) = std::fs::read_to_string(settings) {
        if let Ok(v) = serde_json::from_str::<serde_json::Value>(&text) {
            if let Some(p) = v.get("model_cache_dir").and_then(|x| x.as_str()) {
                if let Some(rest) = p.strip_prefix("~/") {
                    return user_home().join(rest);
                }
                if !p.is_empty() {
                    return PathBuf::from(p);
                }
            }
        }
    }
    user_home().join(".cache").join("ysocial_models")
}

/// Only the folders YSocial's model download creates are ever removed.
fn model_dirs(root: &Path) -> Vec<PathBuf> {
    ["torch", "huggingface"].iter().map(|d| root.join(d)).filter(|p| p.is_dir()).collect()
}

fn dir_size(p: &Path) -> u64 {
    let Ok(rd) = std::fs::read_dir(p) else { return 0 };
    rd.flatten()
        .map(|e| match e.metadata() {
            Ok(m) if m.is_dir() => dir_size(&e.path()),
            Ok(m) => m.len(),
            Err(_) => 0,
        })
        .sum()
}

/// "<path>\t<bytes>" when toxicity models are present on disk, else "".
#[tauri::command]
fn toxicity_models(home: String) -> String {
    let root = models_root(Path::new(&home));
    let dirs = model_dirs(&root);
    if dirs.is_empty() {
        return String::new();
    }
    format!("{}\t{}", root.display(), dirs.iter().map(|d| dir_size(d)).sum::<u64>())
}

/// Open a project link in the system browser (allow-listed addresses only).
#[tauri::command]
fn open_url(url: String) -> Result<(), String> {
    let ok = url == "https://y-not.social"
        || url.starts_with("https://y-not.social/")
        || url.starts_with("https://github.com/YSocialTwin/");
    if !ok {
        return Err("address not allowed".into());
    }
    open_in_browser(&url);
    Ok(())
}

/// Add the optional toxicity extra to an existing installation. The requirement list
/// is read from the installed package, so it always matches the installed version.
#[tauri::command]
async fn install_toxicity(app: AppHandle, home: String) -> Result<(), String> {
    tauri::async_runtime::spawn_blocking(move || {
        let home = PathBuf::from(&home);
        let runtime = home.join("runtime");
        let py = venv_python(&home);
        if !py.exists() {
            return Err("YSocial is not installed in this folder".into());
        }
        let code = r#"import importlib.metadata as m
for r in (m.requires('ysocial') or []):
    spec, _, marker = r.partition(';')
    if 'toxicity' in marker:
        print(spec.strip())"#;
        let out = new_cmd(&py).args(["-c", code]).output().map_err(|e| e.to_string())?;
        let reqs: Vec<String> = String::from_utf8_lossy(&out.stdout)
            .lines().map(|l| l.trim().to_string()).filter(|l| !l.is_empty()).collect();
        if reqs.is_empty() {
            return Err("This YSocial version has no toxicity component".into());
        }
        let uv = resource_file(&app, if cfg!(windows) { "uv.exe" } else { "uv" })?;
        let mut c = new_cmd(&uv);
        c.args(["pip", "install", "--python"]).arg(&py);
        let cons = runtime.join("constraints.txt");
        if cons.exists() {
            c.arg("--constraint").arg(&cons);
        }
        c.args(["--extra-index-url", TORCH_CPU_INDEX, "--index-strategy", "unsafe-best-match"]);
        c.args(&reqs).env("UV_PYTHON_INSTALL_DIR", runtime.join("python")).env("UV_PYTHON_INSTALL_BIN", "0").env("YSOCIAL_HOME", &home);
        run_step(&app, "Installing toxicity detection", &mut c)?;
        let _ = app.emit("progress", "== Done");
        Ok(())
    })
    .await
    .map_err(|e| e.to_string())?
}

/// Remove YSocial from this computer. The program (managed Python, packages) is
/// always removed; the data folder content (experiments, databases, settings) only
/// when `delete_data` is set. A running instance is stopped first.
#[tauri::command]
async fn uninstall(
    app: AppHandle, home: String, host: String, port: u16, delete_data: bool, delete_models: bool,
) -> Result<(), String> {
    tauri::async_runtime::spawn_blocking(move || {
        let home = PathBuf::from(&home);
        let runtime = home.join("runtime");
        // Safety: only touch a folder that really is a YSocial home.
        if !runtime.join("venv").exists() || home.components().count() < 3 {
            return Err("This folder does not look like a YSocial installation".into());
        }
        stop_service(&app, &home, &host, port, true)?;
        let _ = app.emit("progress", "== Removing YSocial");
        // Models first: their location may be recorded in the data folder's settings.
        if delete_models {
            let root = models_root(&home);
            for d in model_dirs(&root) {
                std::fs::remove_dir_all(&d).map_err(|e| e.to_string())?;
            }
            let _ = std::fs::remove_dir(&root); // only if empty
        }
        if delete_data {
            std::fs::remove_dir_all(&home).map_err(|e| e.to_string())?;
        } else {
            std::fs::remove_dir_all(&runtime).map_err(|e| e.to_string())?;
            let _ = std::fs::remove_file(pid_file(&home));
        }
        let _ = app.emit("progress", "YSocial removed.");
        Ok(())
    })
    .await
    .map_err(|e| e.to_string())?
}

fn log_tail(path: &Path, n: usize) -> String {
    // Lossy: Windows tools may write non-UTF-8 bytes, and a strict read would hide the whole log.
    let text = std::fs::read(path).map(|b| String::from_utf8_lossy(&b).into_owned()).unwrap_or_default();
    let lines: Vec<&str> = text.lines().collect();
    lines[lines.len().saturating_sub(n)..].join("\n")
}

const APP_WINDOW: &str = "ysocial-app";

/// Advanced launch options: the same flags as the `ysocial` command line.
#[derive(Deserialize, Default)]
#[serde(default)]
struct LaunchOptions {
    host: String,
    port: u16,
    debug: bool,
    /// "sqlite" | "postgresql"
    db: String,
    /// "", "ollama", "vllm" or host:port
    llm_backend: String,
    /// `-n`: do not launch the Jupyter notebook server
    no_notebook: bool,
    /// `-e`: development mode (private plugin repositories)
    development: bool,
    /// Extra raw arguments (whitespace separated, no quoting)
    extra_args: String,
    /// Open in a borderless application window instead of the system browser
    app_window: bool,
    /// Serve requests in parallel (`YSOCIAL_THREADED`)
    threaded: bool,
}

fn build_args(o: &LaunchOptions) -> Result<Vec<String>, String> {
    if o.port == 0 {
        return Err("Invalid port".into());
    }
    let host = if o.host.trim().is_empty() { "127.0.0.1" } else { o.host.trim() };
    if host.chars().any(|c| c.is_whitespace()) {
        return Err("Invalid host".into());
    }
    let mut args = vec![
        "--host".to_string(),
        host.to_string(),
        "--port".to_string(),
        o.port.to_string(),
    ];
    match o.db.as_str() {
        "" | "sqlite" => {}
        "postgresql" => args.extend(["--db".to_string(), "postgresql".to_string()]),
        other => return Err(format!("Unsupported database: {other}")),
    }
    if !o.llm_backend.trim().is_empty() {
        args.extend(["--llm-backend".to_string(), o.llm_backend.trim().to_string()]);
    }
    if o.debug {
        args.push("--debug".into());
    }
    if o.no_notebook {
        args.push("--no_notebook".into());
    }
    if o.development {
        args.push("--development".into());
    }
    args.extend(o.extra_args.split_whitespace().map(String::from));
    Ok(args)
}

/// Runs in the top frame only: links inside YSocial stay in the window (also those
/// with target=_blank), links to other sites become `window.open`, which the
/// native side hands to the system browser (see `on_new_window`).
const LINK_SCRIPT: &str = r#"
(function () {
  if (window.top !== window) return;
  var origin = location.origin;
  var nativeOpen = window.open.bind(window);
  function sameOrigin(href) {
    try { return new URL(href, location.href).origin === origin; } catch (e) { return false; }
  }
  window.open = function (url, target, features) {
    if (url && sameOrigin(url)) { location.href = new URL(url, location.href).href; return null; }
    return nativeOpen(url, target, features);
  };
  document.addEventListener('click', function (e) {
    var a = e.target && e.target.closest ? e.target.closest('a[href]') : null;
    if (!a || e.defaultPrevented) return;
    var href = a.getAttribute('href') || '';
    if (/^(javascript:|#|mailto:|tel:)/i.test(href)) return;
    if (sameOrigin(a.href)) {
      if (a.target === '_blank') { e.preventDefault(); location.href = a.href; }
    } else if (/^https?:/i.test(a.href)) {
      e.preventDefault();
      nativeOpen(a.href, '_blank');
    }
  }, true);
})();
"#;

/// Shown over the page as soon as the app window is asked to close: stopping the
/// services takes a while and the window must not look frozen meanwhile.
const CLOSING_OVERLAY: &str = r#"
(function () {
  if (document.getElementById('ys-closing')) return;
  var it = /^it/i.test(document.documentElement.lang || navigator.language || '');
  var title = it ? 'Chiusura di YSocial in corso…' : 'Closing YSocial…';
  var sub = it ? 'Sto arrestando i servizi in modo ordinato. La finestra si chiuderà da sola, non serve fare nulla.'
               : 'Shutting the services down cleanly. This window will close by itself, no action needed.';
  var st = document.createElement('style');
  st.textContent = '@keyframes ys-spin{to{transform:rotate(360deg)}}' +
    '#ys-closing{position:fixed;inset:0;z-index:2147483647;display:flex;flex-direction:column;align-items:center;' +
    'justify-content:center;gap:14px;padding:24px;text-align:center;background:rgba(14,20,34,.88);color:#fff;' +
    'font:500 17px/1.4 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;backdrop-filter:blur(6px);' +
    'cursor:progress}#ys-closing small{display:block;max-width:420px;font:400 13px/1.5 inherit;opacity:.75}' +
    '#ys-closing i{width:34px;height:34px;border:3px solid rgba(255,255,255,.25);border-top-color:#fff;' +
    'border-radius:50%;animation:ys-spin .9s linear infinite}';
  var d = document.createElement('div');
  d.id = 'ys-closing';
  d.innerHTML = '<i></i><div>' + title + '<small>' + sub + '</small></div>';
  (document.head || document.documentElement).appendChild(st);
  (document.body || document.documentElement).appendChild(d);
})();
"#;

/// Set while the app window is shutting down, so repeated close clicks do nothing.
static CLOSING: AtomicBool = AtomicBool::new(false);

/// Where each running download is being saved (macOS does not report the path when it ends).
static DOWNLOAD_TARGETS: Mutex<Vec<(String, PathBuf)>> = Mutex::new(Vec::new());

/// Small notice at the bottom right of the page: a download started, ended, failed or was
/// cancelled. Texts are in English and Italian, chosen from the page language.
fn download_toast<R: tauri::Runtime>(webview: &tauri::Webview<R>, kind: &str, name: &str, path: &str) {
    let js = format!(
        r#"(function () {{
  var kind = {kind}, name = {name}, path = {path};
  var it = /^it/i.test(document.documentElement.lang || navigator.language || '');
  var T = {{
    start: [it ? 'Download in corso: ' : 'Downloading: ', it ? 'Il file viene salvato nella cartella scelta.' : 'The file is being saved to the folder you chose.'],
    done: [it ? 'Download completato' : 'Download complete', path],
    fail: [it ? 'Download non riuscito' : 'Download failed', it ? 'Riprova dalla pagina delle notifiche.' : 'Try again from the notifications page.'],
    cancel: [it ? 'Download annullato' : 'Download cancelled', '']
  }}[kind];
  if (!T) return;
  var st = document.getElementById('ys-dl-style');
  if (!st) {{
    st = document.createElement('style'); st.id = 'ys-dl-style';
    st.textContent = '@keyframes ys-dl-run{{0%{{margin-left:-40%}}100%{{margin-left:100%}}}}' +
      '#ys-dl{{position:fixed;right:18px;bottom:18px;z-index:2147483646;max-width:380px;padding:14px 16px;border-radius:12px;' +
      'background:rgba(14,20,34,.94);color:#fff;font:500 14px/1.4 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;' +
      'box-shadow:0 10px 30px rgba(0,0,0,.35);border-left:4px solid #4dabf7}}' +
      '#ys-dl.done{{border-left-color:#51cf66}}#ys-dl.fail{{border-left-color:#ff6b6b}}#ys-dl.cancel{{border-left-color:#adb5bd}}' +
      '#ys-dl small{{display:block;margin-top:4px;font-weight:400;opacity:.8;word-break:break-all}}' +
      '#ys-dl i{{display:block;height:3px;margin-top:8px;border-radius:2px;background:rgba(255,255,255,.2);overflow:hidden}}' +
      '#ys-dl i b{{display:block;width:40%;height:100%;background:#4dabf7;animation:ys-dl-run 1.1s linear infinite}}';
    (document.head || document.documentElement).appendChild(st);
  }}
  var d = document.getElementById('ys-dl');
  if (!d) {{ d = document.createElement('div'); d.id = 'ys-dl'; d.setAttribute('role', 'status'); (document.body || document.documentElement).appendChild(d); }}
  clearTimeout(d._t);
  d.className = kind;
  d.textContent = '';
  var h = document.createElement('div'); h.textContent = T[0] + (kind === 'start' ? name : ''); d.appendChild(h);
  if (T[1]) {{ var s = document.createElement('small'); s.textContent = T[1]; d.appendChild(s); }}
  if (kind === 'start') {{ var b = document.createElement('i'); b.innerHTML = '<b></b>'; d.appendChild(b); }}
  else d._t = setTimeout(function () {{ if (d.parentNode) d.parentNode.removeChild(d); }}, kind === 'done' ? 12000 : 6000);
}})();"#,
        kind = serde_json::to_string(kind).unwrap_or_default(),
        name = serde_json::to_string(name).unwrap_or_default(),
        path = serde_json::to_string(path).unwrap_or_default(),
    );
    let _ = webview.eval(js);
}

/// Downloads started from the YSocial window (experiment exports, files from the admin
/// panel): ask where to save the file, then show when it starts and when it is done.
fn on_app_download<R: tauri::Runtime>(webview: tauri::Webview<R>, event: tauri::webview::DownloadEvent<'_>) -> bool {
    match event {
        tauri::webview::DownloadEvent::Requested { url, destination } => {
            let name = destination
                .file_name()
                .map(|n| n.to_string_lossy().into_owned())
                .unwrap_or_else(|| "download".to_string());
            let mut dialog = rfd::FileDialog::new().set_file_name(name.as_str());
            if let Some(dir) = destination.parent() {
                dialog = dialog.set_directory(dir);
            }
            match dialog.save_file() {
                Some(path) => {
                    if let Ok(mut targets) = DOWNLOAD_TARGETS.lock() {
                        targets.push((url.to_string(), path.clone()));
                    }
                    let shown = path.file_name().map(|n| n.to_string_lossy().into_owned()).unwrap_or(name);
                    *destination = path;
                    download_toast(&webview, "start", &shown, "");
                    true
                }
                None => {
                    download_toast(&webview, "cancel", &name, "");
                    false
                }
            }
        }
        tauri::webview::DownloadEvent::Finished { url, path, success } => {
            let remembered = DOWNLOAD_TARGETS.lock().ok().and_then(|mut targets| {
                let key = url.to_string();
                targets.iter().position(|(u, _)| *u == key).map(|i| targets.remove(i).1)
            });
            let shown = path.or(remembered).map(|p| p.display().to_string()).unwrap_or_default();
            download_toast(&webview, if success { "done" } else { "fail" }, "", &shown);
            true
        }
        _ => true,
    }
}

/// Open YSocial in a native window without browser chrome (address bar, tabs).
/// Embedded third-party frames (e.g. payment widgets) load normally; clicks to other
/// sites and new-window requests open in the system browser.
fn open_app_window(app: &AppHandle, url: &str, home: PathBuf, host: String, port: u16) -> Result<(), String> {
    if let Some(w) = app.get_webview_window(APP_WINDOW) {
        let _ = w.set_focus();
        return Ok(());
    }
    let parsed: tauri::Url = url.parse().map_err(|e| format!("{e}"))?;
    let local = parsed.host_str().unwrap_or("").to_string();
    let window = WebviewWindowBuilder::new(app, APP_WINDOW, WebviewUrl::External(parsed))
        .title("YSocial")
        .inner_size(1360.0, 880.0)
        .min_inner_size(900.0, 600.0)
        .focused(true)
        .initialization_script(LINK_SCRIPT)
        .on_download(on_app_download)
        .on_new_window(move |target, _features| {
            if target.host_str().map(|h| h != local).unwrap_or(true)
                && matches!(target.scheme(), "http" | "https")
            {
                open_in_browser(target.as_str());
            }
            tauri::webview::NewWindowResponse::Deny
        })
        .build()
        .map_err(|e| e.to_string())?;
    let _ = window.set_focus();
    // Closing the application window ends YSocial and everything it started
    // (only if this launcher started it: it needs the pid file).
    let handle = app.clone();
    window.on_window_event(move |event| match event {
        tauri::WindowEvent::CloseRequested { api, .. } => {
            // Keep the window (and the process) alive until YSocial has stopped:
            // the launcher window may already be gone, so this process must not exit early.
            api.prevent_close();
            if CLOSING.swap(true, Ordering::SeqCst) {
                return; // already shutting down
            }
            if let Some(w) = handle.get_webview_window(APP_WINDOW) {
                let _ = w.eval(CLOSING_OVERLAY);
            }
            let (app, home, host) = (handle.clone(), home.clone(), host.clone());
            std::thread::spawn(move || {
                if read_pid(&home).is_some() {
                    let _ = stop_service(&app, &home, &host, port, false);
                }
                if let Some(w) = app.get_webview_window(APP_WINDOW) {
                    let _ = w.destroy();
                }
                if app.webview_windows().keys().all(|k| k == APP_WINDOW) {
                    app.exit(0);
                }
            });
        }
        _ => {}
    });
    Ok(())
}

#[tauri::command]
async fn launch(app: AppHandle, home: String, opts: LaunchOptions) -> Result<String, String> {
    tauri::async_runtime::spawn_blocking(move || {
        let home = PathBuf::from(&home);
        let exe = venv_ysocial(&home);
        if !exe.exists() {
            return Err("YSocial is not installed in this folder".into());
        }
        let args = build_args(&opts)?;
        let shown = probe_host(&opts.host);
        let url = format!("http://{}:{}", if shown == "127.0.0.1" { "localhost".to_string() } else { shown }, opts.port);
        let log_dir = home.join("logs");
        std::fs::create_dir_all(&log_dir).map_err(|e| e.to_string())?;
        let log_path = log_dir.join("launch.log");
        let mut child = None;
        if !port_open(&opts.host, opts.port) {
            // Child output goes to <home>/logs/launch.log so failures are diagnosable.
            let out = std::fs::File::create(&log_path).map_err(|e| e.to_string())?;
            let err = out.try_clone().map_err(|e| e.to_string())?;
            let mut cmd = new_cmd(&exe);
            #[cfg(unix)]
            {
                use std::os::unix::process::CommandExt;
                cmd.process_group(0); // own group: lets stop kill every child
            }
            let spawned = cmd
                .args(&args)
                .env("YSOCIAL_HOME", &home)
                .env("PYTHONUNBUFFERED", "1")
                .env("PYTHONUTF8", "1")
                .env("PYTHONIOENCODING", "utf-8")
                .env("YSOCIAL_THREADED", if opts.threaded { "1" } else { "0" })
                .current_dir(&home)
                .stdin(Stdio::null())
                .stdout(Stdio::from(out))
                .stderr(Stdio::from(err))
                .spawn()
                .map_err(|e| e.to_string())?;
            let _ = std::fs::write(pid_file(&home), spawned.id().to_string());
            child = Some(spawned);
        }
        let _ = app.emit(
            "progress",
            format!("Starting YSocial: ysocial {} (log: {})", args.join(" "), log_path.display()),
        );
        let start = Instant::now();
        while start.elapsed() < Duration::from_secs(180) {
            if port_open(&opts.host, opts.port) {
                if opts.app_window {
                    open_app_window(&app, &url, home.clone(), opts.host.clone(), opts.port)?;
                    // The app window now owns YSocial's lifetime: the launcher is no longer needed.
                    if let Some(w) = app.get_webview_window("main") {
                        let _ = w.close();
                    }
                    // Hand the focus to the app window: otherwise on macOS the first click
                    // only activates the window and every link needs a second click.
                    if let Some(w) = app.get_webview_window(APP_WINDOW) {
                        let _ = w.set_focus();
                    }
                } else {
                    open_in_browser(&url);
                }
                return Ok(url);
            }
            if let Some(c) = child.as_mut() {
                if let Ok(Some(status)) = c.try_wait() {
                    let _ = std::fs::remove_file(pid_file(&home));
                    return Err(format!(
                        "YSocial exited immediately ({status}). Last log lines:\n{}",
                        log_tail(&log_path, 25)
                    ));
                }
            }
            std::thread::sleep(Duration::from_millis(500));
        }
        Err(format!(
            "YSocial did not start within 3 minutes. Last log lines:\n{}",
            log_tail(&log_path, 25)
        ))
    })
    .await
    .map_err(|e| e.to_string())?
}

/// Launcher settings (advanced options) are stored as JSON next to the data.
#[tauri::command]
fn load_settings(home: String) -> String {
    std::fs::read_to_string(PathBuf::from(home).join("launcher.json")).unwrap_or_default()
}

#[tauri::command]
fn save_settings(home: String, json: String) -> Result<(), String> {
    let home = PathBuf::from(home);
    std::fs::create_dir_all(&home).map_err(|e| e.to_string())?;
    std::fs::write(home.join("launcher.json"), json).map_err(|e| e.to_string())
}

fn main() {
    tauri::Builder::default()
        .invoke_handler(tauri::generate_handler![
            default_home,
            is_installed,
            install,
            launch,
            is_running,
            stop,
            uninstall,
            app_version,
            toxicity_models,
            open_url,
            install_toxicity,
            installed_info,
            fetch_latest_release,
            update,
            load_settings,
            save_settings
        ])
        .run(tauri::generate_context!())
        .expect("error while running the YSocial installer");
}
