# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller specification file for YSocial application.

This spec file bundles the entire YSocial application including:
- Main application code (y_web package)
- External dependencies (YServer, YClient submodules)
- Static files (CSS, JS, images, templates)
- Data files (database schemas, prompts)
- Configuration files
"""

import os
import sys
from PyInstaller.utils.hooks import (
    collect_data_files,
    collect_submodules,
    copy_metadata,
)

block_cipher = None

# Get the base directory
basedir = os.path.abspath(SPECPATH)

# Collect all submodules for key packages
hidden_imports = [
    "nltk",
    "nltk.data",
    "sqlalchemy.sql.default_comparator",
    "sqlalchemy.ext.baked",
    "flask",
    "flask_login",
    "flask_sqlalchemy",
    "flask_wtf",
    "wtforms",
    "bs4",
    "feedparser",
    "requests",
    "werkzeug",
    "jinja2",
    "markupsafe",
    "cryptography",
    "openai",
    "ollama",
    "pyautogen",
    "perspective",
    "networkx",
    "numpy",
    "pillow",
    "psutil",
    "ysights",
    "jupyterlab",
    "gunicorn",
    "gevent",
    "psycopg2",
    "sqlalchemy_utils",
    "email_validator",
    "faker",
    "colorama",
    "tqdm",
    "pygments",
    "sklearn",
    "sklearn.utils",
    "scipy",
    "anyio",
    "httpx",
    "httpcore",
    "sniffio",
    "h11",
    "webview",
    "webview.platforms",
]

# Collect all submodules for important packages
hidden_imports += collect_submodules("flask")
hidden_imports += collect_submodules("flask_login")
hidden_imports += collect_submodules("flask_sqlalchemy")
hidden_imports += collect_submodules("sqlalchemy")
hidden_imports += collect_submodules("wtforms")
hidden_imports += collect_submodules("nltk")
hidden_imports += collect_submodules("bs4")
hidden_imports += collect_submodules("openai")
hidden_imports += collect_submodules("pyautogen")
hidden_imports += collect_submodules("ysights")
hidden_imports += collect_submodules("sklearn")
hidden_imports += collect_submodules("webview")

# Data files to include
datas = []

# Add NLTK data
datas += collect_data_files("nltk")

# Collect package metadata for packages that use importlib.metadata
# This fixes "PackageNotFoundError: No package metadata was found for X" errors
for pkg in [
    "anyio",
    "openai",
    "httpx",
    "httpcore",
    "sniffio",
    "h11",
    "certifi",
    "idna",
    "flask",
    "werkzeug",
    "jinja2",
    "click",
    "itsdangerous",
    "flask_login",
    "flask_sqlalchemy",
    "wtforms",
    "requests",
    "urllib3",
    "charset_normalizer",
    "pygments",
    "ysights",
    "pywebview",
]:
    try:
        datas += copy_metadata(pkg)
    except Exception:
        pass  # Package might not be installed
        pass  # Package might not be installed

# Add y_web package data files
datas += [
    (os.path.join(basedir, "y_web", "static"), "y_web/static"),
    (os.path.join(basedir, "y_web", "templates"), "y_web/templates"),
    (os.path.join(basedir, "data_schema"), "data_schema"),
    (os.path.join(basedir, "config_files"), "config_files"),
]

# Add images directory for splash screen
if os.path.exists(os.path.join(basedir, "images")):
    datas += [(os.path.join(basedir, "images"), "images")]

# Add VERSION file
version_file_path = os.path.join(basedir, "VERSION")
if os.path.exists(version_file_path):
    datas += [(version_file_path, ".")]

# PyInstaller utils are now part of y_web package and will be included automatically
# No need to explicitly add splash_screen.py and installation_id.py as separate files

# Add the client process runner script (executed as subprocess, not imported)
runner_script_path = os.path.join(
    basedir, "y_web", "utils", "y_client_process_runner.py"
)
if os.path.exists(runner_script_path):
    datas += [(runner_script_path, "y_web/utils")]

# Add sample notebook template
sample_notebook_path = os.path.join(basedir, "y_web", "utils", "sample_notebook")
if os.path.exists(sample_notebook_path):
    datas += [(sample_notebook_path, "y_web/utils/sample_notebook")]

# Add database schema directory
if os.path.exists(os.path.join(basedir, "y_web", "db")):
    datas += [(os.path.join(basedir, "y_web", "db"), "y_web/db")]

# Add external submodules if they exist
for submodule in ["YServer", "YClient", "YServerReddit", "YClientReddit"]:
    submodule_path = os.path.join(basedir, "external", submodule)
    if os.path.exists(submodule_path) and os.listdir(submodule_path):
        datas += [(submodule_path, f"external/{submodule}")]

a = Analysis(
    ["y_social_launcher.py"],
    pathex=[basedir],
    binaries=[],
    datas=datas,
    hiddenimports=hidden_imports,
    hookspath=[
        os.path.join(basedir, "y_web", "pyinstaller_utils", "pyinstaller_hooks")
    ],
    hooksconfig={},
    runtime_hooks=[
        os.path.join(
            basedir,
            "y_web",
            "pyinstaller_utils",
            "pyinstaller_hooks",
            "runtime_hook_nltk.py",
        )
    ],
    excludes=[
        "matplotlib",
        "pandas",
        "pytest",
        "IPython",
        "notebook",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="YSocial",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join(basedir, "images", "YSocial_ico.png"),
)
