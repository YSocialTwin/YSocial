"""
Ollama LLM server management utilities.

Provides functions for checking, starting, and managing the Ollama local LLM
server, including model download and deletion operations.
"""

import re
import subprocess
import time
from multiprocessing import Process

import requests
from ollama import Client as oclient

from y_web import db
from y_web.models import Ollama_Pull

# Dictionary to track ongoing Ollama model download processes
ollama_processes = {}


def is_ollama_installed():
    # Step 1: Check if Ollama is installed
    """Handle is ollama installed operation."""
    try:
        subprocess.run(
            ["ollama", "--version"], capture_output=True, text=True, check=True
        )
        print("Ollama is installed.")
        return True
    except FileNotFoundError:
        print("Ollama is not installed.")
        return False
    except subprocess.CalledProcessError as e:
        print(f"Error checking Ollama installation: {e}")
        return False


def is_ollama_running():
    # Step 2: Check if Ollama is running
    """Handle is ollama running operation."""
    try:
        response = requests.get("http://127.0.0.1:11434/api/version")
        if response.status_code == 200:
            # print("Ollama is running.")
            return True
        else:
            # print(
            #    f"Ollama responded but not running correctly. Status: {response.status_code}"
            # )
            return False
    except requests.ConnectionError:
        # print("Ollama is not running or cannot be reached.")
        return False


def start_ollama_server():
    """Handle start ollama server operation."""
    if is_ollama_installed():
        if not is_ollama_running():
            screen_command = f"screen -dmS ollama ollama serve"

            print(f"Starting ollama server...")
            subprocess.run(screen_command, shell=True, check=True)

            # Wait for the server to start
            time.sleep(5)
        else:
            print("Ollama is already running.")
    else:
        print("Ollama is not installed.")


def pull_ollama_model(model_name):
    """Handle pull ollama model operation."""
    if is_ollama_running():
        process = Process(target=start_ollama_pull, args=(model_name,))
        process.start()
        ollama_processes[model_name] = process


def start_ollama_pull(model_name):
    """
    Start downloading an Ollama model in background.

    Args:
        model_name: Name of model to download
    """
    ol_client = oclient(
        host="http://127.0.0.1:11434", headers={"x-some-header": "some-value"}
    )

    for progress in ol_client.pull(model_name, stream=True):
        model = Ollama_Pull.query.filter_by(model_name=model_name).first()
        if not model:
            model = Ollama_Pull(model_name=model_name, status=0)
            db.session.add(model)
            db.session.commit()

        total = progress.get("total")
        completed = progress.get("completed")
        if completed is not None:
            current = float(completed) / float(total)
            # update the model status
            model = Ollama_Pull.query.filter_by(model_name=model_name).first()
            model.status = current
            db.session.commit()


def get_ollama_models():
    """
    Get list of installed Ollama models.

    Returns:
        List of available model names
    """
    pattern = r"model='(.*?)'"
    models = []

    ol_client = oclient(
        host="http://0.0.0.0:11434", headers={"x-some-header": "some-value"}
    )

    # Extract all model values
    for i in ol_client.list():
        models = re.findall(pattern, str(i))

    models = [m for m in models if len(m) > 0]
    return models


def delete_ollama_model(model_name):
    """
    Delete an Ollama model from the system.

    Args:
        model_name: Name of model to delete
    """
    ol_client = oclient(
        host="http://0.0.0.0:11434", headers={"x-some-header": "some-value"}
    )

    ol_client.delete(model_name)


def delete_model_pull(model_name):
    """
    Cancel an ongoing model download.

    Args:
        model_name: Name of model to cancel download for
    """
    if model_name in ollama_processes:
        process = ollama_processes[model_name]
        process.terminate()
        process.join()

    model = Ollama_Pull.query.filter_by(model_name=model_name).first()
    db.session.delete(model)
    db.session.commit()
