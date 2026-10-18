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
    let stderr = child.stderr.take();
    let app2 = app.clone();
    let t = std::thread::spawn(move || {
        if let Some(s) = stderr {
            for line in BufReader::new(s).lines().flatten() {
                let _ = app2.emit("progress", line);
            }
        }
    });
    if let Some(s) = child.stdout.take() {
        for line in BufReader::new(s).lines().flatten() {
            let _ = app.emit("progress", line);
        }
    }
    let _ = t.join();
    let status = child.wait().map_err(|e| e.to_string())?;
    if status.success() {
        Ok(())
    } else {
        Err(format!("{label} failed ({status})"))
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
            c.env("UV_PYTHON_INSTALL_DIR", &py_dir).env("YSOCIAL_HOME", &home);
        };

        let mut c = Command::new(&uv);
        c.args(["python", "install", PYTHON_VERSION]);
        base(&mut c);
        run_step(&app, "Installing Python", &mut c)?;

        let mut c = Command::new(&uv);
        c.args(["venv", "--seed", "--python", PYTHON_VERSION]).arg(&venv);
        base(&mut c);
        run_step(&app, "Creating environment", &mut c)?;

        let mut c = Command::new(&uv);
        c.args(["pip", "install", "--python"]).arg(venv_python(&home));
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
        Command::new("open").arg(url).spawn()
    } else if cfg!(target_os = "windows") {
        Command::new("cmd").args(["/C", "start", "", url]).spawn()
    } else {
        Command::new("xdg-open").arg(url).spawn()
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
        Command::new("tasklist")
            .args(["/FI", &format!("PID eq {pid}"), "/NH"])
            .output()
            .map(|o| String::from_utf8_lossy(&o.stdout).contains(&pid.to_string()))
            .unwrap_or(false)
    } else {
        Command::new("kill")
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

/// Stop YSocial: SIGTERM (clean shutdown: experiments and Jupyter are stopped by
/// YSocial itself), then SIGKILL after 15 s. Windows: taskkill of the process tree.
#[tauri::command]
async fn stop(app: AppHandle, home: String, host: String, port: u16) -> Result<(), String> {
    tauri::async_runtime::spawn_blocking(move || {
        let home = PathBuf::from(&home);
        let Some(pid) = read_pid(&home) else {
            return if port_open(&host, port) {
                Err(format!(
                    "Something is listening on port {port}, but it was not started by this installer"
                ))
            } else {
                Ok(())
            };
        };
        let _ = app.emit("progress", format!("Stopping YSocial (pid {pid})..."));
        if cfg!(target_os = "windows") {
            let _ = Command::new("taskkill").args(["/PID", &pid.to_string(), "/T", "/F"]).status();
        } else {
            let _ = Command::new("kill").args(["-TERM", &pid.to_string()]).status();
        }
        let start = Instant::now();
        while start.elapsed() < Duration::from_secs(15) {
            if !pid_alive(pid) {
                break;
            }
            std::thread::sleep(Duration::from_millis(300));
        }
        if pid_alive(pid) && !cfg!(target_os = "windows") {
            let _ = app.emit("progress", "Forcing stop...");
            let _ = Command::new("kill").args(["-KILL", &pid.to_string()]).status();
            std::thread::sleep(Duration::from_millis(500));
        }
        let _ = std::fs::remove_file(pid_file(&home));
        if pid_alive(pid) {
            return Err("Could not stop YSocial".into());
        }
        if let Some(w) = app.get_webview_window(APP_WINDOW) {
            let _ = w.close();
        }
        let _ = app.emit("progress", "YSocial stopped.");
        Ok(())
    })
    .await
    .map_err(|e| e.to_string())?
}

fn log_tail(path: &Path, n: usize) -> String {
    let text = std::fs::read_to_string(path).unwrap_or_default();
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

/// Open YSocial in a native window without browser chrome (address bar, tabs).
/// Embedded third-party frames (e.g. payment widgets) load normally; clicks to other
/// sites and new-window requests open in the system browser.
fn open_app_window(app: &AppHandle, url: &str) -> Result<(), String> {
    if let Some(w) = app.get_webview_window(APP_WINDOW) {
        let _ = w.set_focus();
        return Ok(());
    }
    let parsed: tauri::Url = url.parse().map_err(|e| format!("{e}"))?;
    let local = parsed.host_str().unwrap_or("").to_string();
    WebviewWindowBuilder::new(app, APP_WINDOW, WebviewUrl::External(parsed))
        .title("YSocial")
        .inner_size(1360.0, 880.0)
        .min_inner_size(900.0, 600.0)
        .initialization_script(LINK_SCRIPT)
        .on_new_window(move |target, _features| {
            if target.host_str().map(|h| h != local).unwrap_or(true)
                && matches!(target.scheme(), "http" | "https")
            {
                open_in_browser(target.as_str());
            }
            tauri::webview::NewWindowResponse::Deny
        })
        .build()
        .map(|_| ())
        .map_err(|e| e.to_string())
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
            let spawned = Command::new(&exe)
                .args(&args)
                .env("YSOCIAL_HOME", &home)
                .env("PYTHONUNBUFFERED", "1")
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
                    open_app_window(&app, &url)?;
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
            load_settings,
            save_settings
        ])
        .run(tauri::generate_context!())
        .expect("error while running the YSocial installer");
}
