import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import psutil

from y_web import db
from y_web.models import Jupyter_instances


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


def ensure_kernel_installed(kernel_name="python3"):
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
                [sys.executable, "-m", "pip", "install", "ipykernel"],
                check=True
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


def start_jupyter(expid, notebook_dir=None):
    """Start Jupyter Lab server

    Args:
        notebook_dir: Path to notebook directory. If None, uses default.
                     If provided as a string, it will be created under experiments/ folder.

    Returns:
        tuple: (success, message, instance_id)
    """

    # Ensure kernel is installed
    ensure_kernel_installed()

    notebook_dir = Path(notebook_dir)
    notebook_dir.mkdir(exist_ok=True, parents=True)

    instances = db.session.query(Jupyter_instances).all()
    JUPYTER_INSTANCES = {
        inst.exp_id: {
            "port": inst.port,
            "process": inst.process,
            "notebook_dir": Path(inst.notebook_dir),
        }
        for inst in instances
    }

    # Check if an instance with this notebook dir is already running
    existing_instance_id = find_instance_by_notebook_dir(notebook_dir)
    if existing_instance_id:
        inst = JUPYTER_INSTANCES[existing_instance_id]
        return (
            True,
            f"Jupyter Lab is already running on port {inst['port']} with this notebook directory",
            existing_instance_id,
        )

    # Find a free port
    port = find_free_port()
    if port is None:
        return False, "No free ports available", None

    try:
        # Start Jupyter Lab with proper configuration for embedding
        cmd = [
            sys.executable,
            "-m",
            "jupyter",
            "lab",
            f"--port={port}",
            f"--ServerApp.token=embed-jupyter-token",
            "--ServerApp.password=",
            "--no-browser",
            f"--notebook-dir={notebook_dir.absolute()}",
            "--ServerApp.allow_origin=*",
            "--ServerApp.disable_check_xsrf=True",
            # Allow frame ancestors for embedding
            '--ServerApp.tornado_settings={"headers":{"Content-Security-Policy":"frame-ancestors *"}}',
            # Disable authentication redirect which can cause issues in iframes
            "--IdentityProvider.token=",
            # Allow remote access
            "--ServerApp.allow_remote_access=True",
            # WebSocket configuration
            "--ServerApp.allow_origin_pat=.*",
        ]

        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            preexec_fn=os.setsid if os.name != "nt" else None,
        )

        # Store instance info
        # update the process to store the pid
        instance = db.session.query(Jupyter_instances).filter_by(exp_id=expid).first()
        instance.port = port
        instance.process = process.pid
        instance.notebook_dir = str(notebook_dir)
        instance.status = "running"
        db.session.commit()

        # Optionally get the new ID
        instance_id = instance.exp_id

        # Wait a bit for Jupyter to start
        time.sleep(3)

        # Check if process is still running
        if process.poll() is None:
            create_notebook_with_template(notebook_dir=str(notebook_dir))

            return True, f"Jupyter Lab started on port {port}", None
        else:
            stderr = process.stderr.read().decode() if process.stderr else ""
            ysession = db.session.query(Jupyter_instances).filter_by(id=instance_id).first()
            ysession.status = "stopped"
            ysession.process = None
            ysession.port = -1
            db.session.commit()
            del JUPYTER_INSTANCES[instance_id]
            return False, f"Failed to start Jupyter Lab: {stderr}", None

    except Exception as e:
        ysession = db.session.query(Jupyter_instances).filter_by(id=instance_id).first()
        ysession.status = "stopped"
        ysession.process = None
        ysession.port = -1
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
        ysession = db.session.query(Jupyter_instances).filter_by(exp_id=instance_id).first()
        ysession.status = "stopped"
        ysession.process = None
        ysession.port = -1
        db.session.commit()
        return True, f"Instance {instance_id} (PID {pid}) stopped gracefully."
    except psutil.TimeoutExpired:
        # Force kill
        try:
            proc.kill()
            ysession = db.session.query(Jupyter_instances).filter_by(exp_id=instance_id).first()
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
            ysession = db.session.query(Jupyter_instances).filter_by(exp_id=instance_id).first()
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
        notebook_content = {
            "cells": [
                {
                    "cell_type": "markdown",
                    "metadata": {},
                    "source": [
                        "# New Notebook\n",
                        "\n",
                        "This notebook was created with predefined imports and setup.",
                    ],
                },
                {
                    "cell_type": "code",
                    "execution_count": None,
                    "metadata": {},
                    "outputs": [],
                    "source": [
                        "# Standard imports\n",
                        "import ysight as ys\n",
                        "import matplotlib.pyplot as plt\n",
                        "\n",
                        "# Display settings\n",
                        "%matplotlib inline\n",
                        "pd.set_option('display.max_columns', None)\n",
                        "\n",
                        "print('Environment ready!')",
                    ],
                },
                {
                    "cell_type": "code",
                    "execution_count": None,
                    "metadata": {},
                    "outputs": [],
                    "source": ["# Your code here"],
                },
            ],
            "metadata": {
                "kernelspec": {
                    "display_name": "Python 3",
                    "language": "python",
                    "name": "python3",
                },
                "language_info": {
                    "codemirror_mode": {"name": "ipython", "version": 3},
                    "file_extension": ".py",
                    "mimetype": "text/x-python",
                    "name": "python",
                    "nbconvert_exporter": "python",
                    "pygments_lexer": "ipython3",
                    "version": "3.8.0",
                },
            },
            "nbformat": 4,
            "nbformat_minor": 4,
        }

        filepath = Path(f"{notebook_dir}{os.sep}{filename}")
        with open(filepath, "w") as f:
            json.dump(notebook_content, f, indent=2)

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
