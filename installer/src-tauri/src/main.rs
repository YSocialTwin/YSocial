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
use tauri::{AppHandle, Emitter, Manager};

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

fn log_tail(path: &Path, n: usize) -> String {
    let text = std::fs::read_to_string(path).unwrap_or_default();
    let lines: Vec<&str> = text.lines().collect();
    lines[lines.len().saturating_sub(n)..].join("\n")
}

#[tauri::command]
async fn launch(app: AppHandle, home: String, port: u16) -> Result<String, String> {
    tauri::async_runtime::spawn_blocking(move || {
        let home = PathBuf::from(&home);
        let exe = venv_ysocial(&home);
        if !exe.exists() {
            return Err("YSocial is not installed in this folder".into());
        }
        let url = format!("http://localhost:{port}");
        let log_dir = home.join("logs");
        std::fs::create_dir_all(&log_dir).map_err(|e| e.to_string())?;
        let log_path = log_dir.join("launch.log");
        let mut child = None;
        if TcpStream::connect(("127.0.0.1", port)).is_err() {
            // Child output goes to <home>/logs/launch.log so failures are diagnosable.
            let out = std::fs::File::create(&log_path).map_err(|e| e.to_string())?;
            let err = out.try_clone().map_err(|e| e.to_string())?;
            child = Some(
                Command::new(&exe)
                    .args(["--host", "127.0.0.1", "--port", &port.to_string()])
                    .env("YSOCIAL_HOME", &home)
                    .env("PYTHONUNBUFFERED", "1")
                    .current_dir(&home)
                    .stdin(Stdio::null())
                    .stdout(Stdio::from(out))
                    .stderr(Stdio::from(err))
                    .spawn()
                    .map_err(|e| e.to_string())?,
            );
        }
        let _ = app.emit("progress", format!("Starting YSocial... (log: {})", log_path.display()));
        let start = Instant::now();
        while start.elapsed() < Duration::from_secs(180) {
            if TcpStream::connect(("127.0.0.1", port)).is_ok() {
                open_in_browser(&url);
                return Ok(url);
            }
            if let Some(c) = child.as_mut() {
                if let Ok(Some(status)) = c.try_wait() {
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

fn main() {
    tauri::Builder::default()
        .invoke_handler(tauri::generate_handler![default_home, is_installed, install, launch])
        .run(tauri::generate_context!())
        .expect("error while running the YSocial installer");
}
