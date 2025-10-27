import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import psutil

from y_web import db
from y_web.models import Exps, Jupyter_instances


def find_free_port(start_port=8889):
    """Find the next free port starting from start_port."""
    # get all jupyter instances from the db
    instances = db.session.query(Jupyter_instances).all()
    JUPYTER_INSTANCES = {
        inst.id: {
            "port": inst.port,
            "process": inst.process,
            "notebook_dir": Path(inst.notebook_dir),
        }
        for inst in instances
    }

    port = start_port
    while port < start_port + 100:  # Check up to 100 ports
        # Check if port is already used by one of our Jupyter instances
        if any(inst["port"] == port for inst in JUPYTER_INSTANCES.values()):
            port += 1
            continue

        # Check if port is in use by any external process
        port_in_use = False
        try:
            for proc in psutil.process_iter(["pid", "name"]):
                try:
                    for conn in proc.connections(kind="inet"):
                        if conn.laddr and conn.laddr.port == port:
                            port_in_use = True
                            break
                    if port_in_use:
                        break
                except (psutil.AccessDenied, psutil.NoSuchProcess):
                    continue
        except Exception as e:
            print(f"Warning: failed to iterate processes: {e}")

        if not port_in_use:
            return port

        port += 1

    return None


def get_jupyter_instances():
    """Get all running Jupyter Lab instances with their details"""
    instances = db.session.query(Jupyter_instances).all()
    JUPYTER_INSTANCES = {
        inst.id: {
            "port": inst.port,
            "process": inst.process,
            "notebook_dir": Path(inst.notebook_dir),
            "exp_id": inst.exp_id,
        }
        for inst in instances
    }

    instances = []
    for instance_id, inst in JUPYTER_INSTANCES.items():
        proc = inst["process"]
        if proc and proc.poll() is None:
            instances.append(
                {
                    "id": instance_id,
                    "port": inst["port"],
                    "notebook_dir": str(inst["notebook_dir"]),
                    "exp_id": inst["exp_id"],
                    "running": True,
                }
            )
        else:
            instances.append(
                {
                    "id": instance_id,
                    "port": inst["port"],
                    "notebook_dir": str(inst["notebook_dir"]),
                    "exp_id": inst["exp_id"],
                    "running": False,
                }
            )
    return instances


def find_instance_by_notebook_dir(notebook_dir):
    """Find an instance with the specified notebook directory"""
    instances = db.session.query(Jupyter_instances).all()
    JUPYTER_INSTANCES = {
        inst.exp_id: {
            "port": inst.port,
            "process": inst.process,
            "notebook_dir": Path(inst.notebook_dir),
            "exp_id": inst.exp_id,
        }
        for inst in instances
    }

    notebook_dir = Path(notebook_dir).absolute()
    for instance_id, inst in JUPYTER_INSTANCES.items():
        if inst["notebook_dir"].absolute() == notebook_dir:
            proc_pid = inst["process"]
            if not proc_pid:
                return None

            try:
                proc = psutil.Process(int(proc_pid))
                if proc.is_running() and proc.status() != psutil.STATUS_ZOMBIE:
                    return instance_id
            except psutil.NoSuchProcess:
                pass

    return None


def ensure_kernel_installed(kernel_name="python3_ysocial"):
    """
    Ensure an IPython kernel is installed and registered in the current environment.

    Steps:
    1. Check if 'ipykernel' module exists.
    2. If not, install it via pip.
    3. Verify that the kernel spec is registered.
    4. If missing, create/register it.
    """
    try:
        # 1. Check if ipykernel is importable
        try:
            __import__("ipykernel")
        except ImportError:
            print("ipykernel not found, installing...")
            subprocess.run(
                [sys.executable, "-m", "pip", "install", "ipykernel"], check=True
            )

        # 2. Check if kernel spec already exists
        result = subprocess.run(
            [sys.executable, "-m", "jupyter", "kernelspec", "list", "--json"],
            capture_output=True,
            text=True,
        )

        if result.returncode == 0:
            data = json.loads(result.stdout)
            kernels = data.get("kernelspecs", {})
            if kernel_name in kernels:
                print(f"Kernel '{kernel_name}' already registered.")
                return True

        # 3. Register the kernel if missing
        print(f"Registering kernel '{kernel_name}'...")
        subprocess.run(
            [
                sys.executable,
                "-m",
                "ipykernel",
                "install",
                "--user",
                "--name",
                kernel_name,
                "--display-name",
                f"Python ({kernel_name})",
            ],
            check=True,
        )

        print(f"Kernel '{kernel_name}' successfully installed and registered.")
        return True

    except subprocess.CalledProcessError as e:
        print(f"Error while installing/registering kernel: {e}")
        return False

    except Exception as e:
        print(f"Unexpected error: {e}")
        return False


def start_jupyter(expid, notebook_dir=None, current_host=None, current_port=5000):
    """Start Jupyter Lab server.

    Args:
        expid: Experiment ID
        notebook_dir: Path to notebook directory. If None, uses default.
        current_host: Flask app host
        current_port: Flask app port

    Returns:
        tuple: (success, message, instance_id)
    """
    from pathlib import Path
    import subprocess, os, sys, time
    import psutil

    # Ensure kernel is installed
    ensure_kernel_installed()

    notebook_dir = Path(notebook_dir)
    notebook_dir.mkdir(parents=True, exist_ok=True)

    # Existing instances
    instances = db.session.query(Jupyter_instances).all()
    JUPYTER_INSTANCES = {
        inst.exp_id: {
            "port": inst.port,
            "process": inst.process,
            "notebook_dir": Path(inst.notebook_dir),
        }
        for inst in instances
    }

    existing_instance_id = find_instance_by_notebook_dir(notebook_dir)
    if existing_instance_id:
        inst = JUPYTER_INSTANCES[existing_instance_id]
        return (
            True,
            f"Jupyter Lab is already running on port {inst['port']} with this notebook directory",
            existing_instance_id,
        )

    port = find_free_port()
    if port is None:
        return False, "No free ports available", None

    exp = db.session.query(Exps).filter_by(idexp=expid).first()

    if "database_server.db" in exp.db_name:
        db_name = f"y_web{os.sep}{exp.db_name}"  # SQLite path
    else:
        db_name = f"postgresql://postgresql:password@localhost:5432/{exp.db_name}"  # PostgreSQL connection string

    # Prepare environment
    env = os.environ.copy()

    env.update({
        "HOME": str(Path.home()),
        "JUPYTER_CONFIG_DIR": str(Path.home() / ".jupyter"),
        "XDG_RUNTIME_DIR": "/tmp",
        "PATH": os.environ.get("PATH", ""),
        "DB": str(os.path.abspath(db_name))
    })

    cmd = [
        sys.executable,
        "-m", "jupyter",
        "lab",
        f"--port={port}",
        "--ServerApp.token=embed-jupyter-token",
        "--ServerApp.password=",
        f"--ServerApp.ip={current_host or '0.0.0.0'}",
        "--no-browser",
        f"--ServerApp.root_dir={notebook_dir.resolve()}",
        f"--ServerApp.allow_origin=http://{current_host}:{current_port}",
        "--ServerApp.allow_origin_pat=.*",
        "--ServerApp.disable_check_xsrf=True",
        "--IdentityProvider.token=",
        "--ServerApp.allow_remote_access=True",
        "--ServerApp.allow_host=*",
        f"--ServerApp.base_url=/jupyter/{expid}/",
        "--ServerApp.trust_xheaders=True",
        # tornado_settings singolo per iframe embedding
        f'--ServerApp.tornado_settings={{"headers": {{"X-Frame-Options": "ALLOWALL", "Content-Security-Policy": "frame-ancestors http://{current_host}:{current_port}"}}}}',
    ]

    try:
        process = subprocess.Popen(
            cmd,
            env=env,
            cwd=str(notebook_dir.parent),  # critical for Ubuntu
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            preexec_fn=os.setsid if os.name != "nt" else None,
            text=True,
        )

        # Store instance info
        instance = db.session.query(Jupyter_instances).filter_by(exp_id=expid).first()
        instance.port = port
        instance.process = process.pid
        instance.notebook_dir = str(notebook_dir)
        instance.status = "running"
        db.session.commit()
        instance_id = instance.exp_id

        startup_timeout = 10  # seconds
        start = time.time()

        stderr_output = []

        while time.time() - start < startup_timeout:
            # Check if the process has terminated
            if process.poll() is not None:
                # Process ended early which usually means an error
                err = "".join(stderr_output) + (process.stderr.read() or "")
                print(f"Process exited early: {err}")

            # Read non-blocking from stderr (just a small chunk)
            line = process.stderr.readline()
            if line:
                stderr_output.append(line)

                # Detect known Jupyter 'certificate of life'
                if "http" in line or "Jupyter" in line:
                    break

            time.sleep(0.5)

        # Final check after wait loop
        if process.poll() is not None:
            err = "".join(stderr_output) + (process.stderr.read() or "")
            print(f"Process exited early: {err}")

        create_notebook_with_template(notebook_dir=str(notebook_dir))
        print(f"Created template notebook")
        return True, f"Jupyter Lab started on port {port}", instance_id

    except Exception as e:
        print(f"Error starting Jupyter Lab: {e}")
        instance = db.session.query(Jupyter_instances).filter_by(exp_id=expid).first()
        if instance:
            instance.status = "stopped"
            instance.process = None
            instance.port = -1
            db.session.commit()
        return False, f"Error starting Jupyter Lab: {str(e)}", None


def stop_process(pid, instance_id):
    try:
        proc = psutil.Process(pid)
    except psutil.NoSuchProcess:
        ysession = db.session.query(Jupyter_instances).filter_by(id=instance_id).first()
        ysession.status = "stopped"
        ysession.process = None
        ysession.port = -1
        db.session.commit()
        return (
            True,
            f"Instance {instance_id}: process {pid} not found (already stopped).",
        )

    try:
        # Graceful terminate
        if os.name != "nt":
            proc.terminate()
        else:
            proc.send_signal(
                signal.CTRL_BREAK_EVENT
                if hasattr(signal, "CTRL_BREAK_EVENT")
                else signal.SIGTERM
            )

        proc.wait(timeout=5)
        ysession = (
            db.session.query(Jupyter_instances).filter_by(exp_id=instance_id).first()
        )
        ysession.status = "stopped"
        ysession.process = None
        ysession.port = -1
        db.session.commit()
        return True, f"Instance {instance_id} (PID {pid}) stopped gracefully."
    except psutil.TimeoutExpired:
        # Force kill
        try:
            proc.kill()
            ysession = (
                db.session.query(Jupyter_instances)
                .filter_by(exp_id=instance_id)
                .first()
            )
            ysession.status = "stopped"
            ysession.process = None
            ysession.port = -1
            db.session.commit()
            return True, f"Instance {instance_id} (PID {pid}) force-stopped."
        except Exception as e:
            return (
                False,
                f"Instance {instance_id} (PID {pid}) could not be killed: {e}",
            )
    except Exception as e:
        return False, f"Error stopping instance {instance_id} (PID {pid}): {e}"


def stop_jupyter(instance_id=None):
    """Stop Jupyter Lab server(s).

    Args:
        instance_id (int, optional): ID of specific instance to stop.
            If None, stops all instances.

    Returns:
        tuple: (success: bool, message: str)
    """
    instances = db.session.query(Jupyter_instances).all()
    JUPYTER_INSTANCES = {
        inst.exp_id: {
            "port": inst.port,
            "pid": inst.process,  # stored as PID in DB
            "notebook_dir": Path(inst.notebook_dir),
        }
        for inst in instances
    }

    instance_id = int(instance_id)

    # Stop one instance
    if instance_id:
        if instance_id not in JUPYTER_INSTANCES:
            return False, f"Instance {instance_id} not found in database."

        inst = JUPYTER_INSTANCES[instance_id]
        pid = inst["pid"]

        if not pid:
            ysession = (
                db.session.query(Jupyter_instances)
                .filter_by(exp_id=instance_id)
                .first()
            )
            ysession.status = "stopped"
            ysession.process = None
            ysession.port = -1
            db.session.commit()
            return True, f"Instance {instance_id} has no PID stored (removed from DB)."

        return stop_process(pid, instance_id)

    # Stop all instances
    if not JUPYTER_INSTANCES:
        return True, "No JupyterLab instances running."

    stopped, failed = [], []
    for inst_id, inst in JUPYTER_INSTANCES.items():
        success, msg = stop_process(inst["pid"], inst_id)
        if success:
            stopped.append(inst_id)
        else:
            failed.append((inst_id, msg))

    if failed:
        failed_msgs = "; ".join(f"{fid}: {msg}" for fid, msg in failed)
        return False, f"Failed to stop some instances: {failed_msgs}"

    return (
        True,
        f"Stopped {len(stopped)} JupyterLab instance(s): {', '.join(map(str, stopped))}",
    )


def create_notebook_with_template(filename="start_here.ipynb", notebook_dir=None):
    """Create a new notebook with predefined cells

    Args:
        filename: Name of the notebook file
        notebook_dir: Directory to create the notebook in. If None, uses default.
                     If provided as a string, it will be created under experiments/ folder.
    """
    # check if file exists

    if (Path(f"{notebook_dir}{os.sep}{filename}")).exists():
        return False, f"Notebook {filename} already exists."

    else:
        # copy notebook template from sample_notebook/start_here.ipynb
        import shutil

        base_notebook = f"y_web{os.sep}utils{os.sep}sample_notebook{os.sep}start_here.ipynb"  # SQLite path
        abs_path = os.path.abspath(base_notebook)
        shutil.copy(abs_path, f"{notebook_dir}{os.sep}{filename}")

    return True


def stop_all_jupyter_instances():
    instances = db.session.query(Jupyter_instances).all()
    for inst in instances:
        if inst.status == "running":
            stop_process(inst.process, inst.exp_id)
            inst.status = "stopped"
            inst.process = None
            inst.port = -1
            db.session.commit()
