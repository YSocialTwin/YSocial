# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller specification file for YSocial application.

This spec file bundles the entire YSocial application including:
- Main application code (y_web package)
- External dependencies (YServer, YClient submodules)
- Static files (CSS, JS, images, templates)
- Data files (database schemas, prompts)
- Configuration files

SIZE OPTIMIZATION STRATEGIES APPLIED:
1. NLTK: Only VADER lexicon included (~1MB vs ~100MB full corpus)
2. Binary stripping: Enabled to remove debug symbols
3. UPX compression: Enabled with proper exclusions
4. Minimal NLTK submodules: Only sentiment.vader imported
5. Test/docs exclusion: Removed unittest, sphinx, pytest, etc.
6. Selective visualization: Excluded seaborn, plotly, bokeh (matplotlib/pandas kept for JupyterLab)

NOTE: matplotlib, pandas, IPython, jupyter, notebook, jupyterlab, setuptools, pip, wheel
are INCLUDED (not excluded) because they are required for JupyterLab data science functionality.
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
    "nltk.sentiment.vader",  # Only import what we need
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
# Only collect minimal NLTK submodules needed for sentiment analysis
hidden_imports += ["nltk.sentiment", "nltk.sentiment.vader"]
hidden_imports += collect_submodules("bs4")
hidden_imports += collect_submodules("openai")
hidden_imports += collect_submodules("pyautogen")
hidden_imports += collect_submodules("ysights")
hidden_imports += collect_submodules("sklearn")
hidden_imports += collect_submodules("webview")

# Data files to include
datas = []

# Add only VADER lexicon from NLTK (not all NLTK data)
# This dramatically reduces size - from ~100MB to ~1MB of NLTK data
print("=" * 60)
print("Collecting NLTK VADER lexicon data...")
print("=" * 60)

vader_collected = False

# Method 1: Try collect_data_files with different subdir patterns
for subdir_pattern in ["sentiment/vader_lexicon", "sentiment", "corpora/vader_lexicon"]:
    try:
        vader_data = collect_data_files(
            "nltk", subdir=subdir_pattern, include_py_files=False
        )
        if vader_data:
            # Filter to only include vader_lexicon files
            vader_files = [
                (src, dst) for src, dst in vader_data if "vader_lexicon" in src.lower()
            ]
            if vader_files:
                datas += vader_files
                print(
                    f"✓ Method 1 SUCCESS: Added {len(vader_files)} VADER files via pattern '{subdir_pattern}'"
                )
                vader_collected = True
                break
    except Exception as e:
        print(f"  Method 1 with '{subdir_pattern}': {e}")

# Method 2: Manual NLTK data path discovery
if not vader_collected:
    print("  Method 1 failed, trying Method 2 (manual discovery)...")
    try:
        import nltk
        import nltk.data

        # Try to find NLTK data directories
        nltk_paths = nltk.data.path
        print(f"  NLTK data paths: {nltk_paths}")

        for nltk_path in nltk_paths:
            if os.path.exists(nltk_path):
                # Look for vader_lexicon in sentiment directory
                vader_dirs = [
                    os.path.join(nltk_path, "sentiment", "vader_lexicon"),
                    os.path.join(nltk_path, "sentiment", "vader_lexicon.zip"),
                    os.path.join(nltk_path, "corpora", "vader_lexicon"),
                    os.path.join(nltk_path, "corpora", "vader_lexicon.zip"),
                ]

                for vader_dir in vader_dirs:
                    if os.path.exists(vader_dir):
                        if os.path.isfile(vader_dir):
                            # It's a zip file
                            datas += [(vader_dir, "nltk_data/sentiment")]
                            print(
                                f"✓ Method 2 SUCCESS: Added VADER lexicon file: {vader_dir}"
                            )
                            vader_collected = True
                            break
                        elif os.path.isdir(vader_dir):
                            # It's a directory, add all files
                            for root, dirs, files in os.walk(vader_dir):
                                for file in files:
                                    src = os.path.join(root, file)
                                    rel_path = os.path.relpath(root, nltk_path)
                                    dst = os.path.join("nltk_data", rel_path)
                                    datas += [(src, dst)]
                            print(
                                f"✓ Method 2 SUCCESS: Added VADER lexicon directory: {vader_dir}"
                            )
                            vader_collected = True
                            break

                if vader_collected:
                    break
    except Exception as e:
        print(f"  Method 2 failed: {e}")

# Method 3: Try using nltk.data.find() with proper handling
if not vader_collected:
    print("  Methods 1-2 failed, trying Method 3 (nltk.data.find)...")
    try:
        import nltk

        vader_resource = nltk.data.find("sentiment/vader_lexicon.zip")
        # Handle different return types
        if hasattr(vader_resource, "__fspath__"):
            vader_path = vader_resource.__fspath__()
        elif hasattr(vader_resource, "path"):
            vader_path = vader_resource.path
        else:
            vader_path = str(vader_resource)

        if vader_path and os.path.exists(vader_path):
            datas += [(vader_path, "nltk_data/sentiment")]
            print(f"✓ Method 3 SUCCESS: Added VADER lexicon: {vader_path}")
            vader_collected = True
    except Exception as e:
        print(f"  Method 3 failed: {e}")

# Final fallback: Collect all sentiment data (still much smaller than full NLTK)
if not vader_collected:
    print("  All methods failed, using fallback (collect all sentiment data)...")
    try:
        sentiment_data = collect_data_files(
            "nltk", subdir="sentiment", include_py_files=False
        )
        if sentiment_data:
            datas += sentiment_data
            print(f"✓ FALLBACK SUCCESS: Added {len(sentiment_data)} sentiment files")
            vader_collected = True
    except Exception as e:
        print(f"  Fallback failed: {e}")

if not vader_collected:
    print("⚠ WARNING: Could not collect VADER lexicon data!")
    print("  Sentiment analysis may not work in the built application.")
    print("  Please ensure NLTK VADER lexicon is downloaded:")
    print("  python -c \"import nltk; nltk.download('vader_lexicon')\"")
else:
    print(f"✓ VADER lexicon collection completed successfully!")

print("=" * 60)

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
    hooksconfig={
        # Disable PyInstaller's auto-generated NLTK runtime hook
        # We use our own custom runtime hook instead
        "nltk": {"no_runtime_hook": True},
    },
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
        # Exclude unused packages to reduce size
        # NOTE: matplotlib, pandas, IPython, notebook, jupyter, jupyterlab, setuptools, pip, wheel
        # are NOT excluded because they are needed for JupyterLab functionality
        "pytest",
        # Exclude unused test modules
        "unittest",
        "test",
        "tests",
        "_pytest",
        # Exclude documentation
        "sphinx",
        "docutils",
        # Exclude unused NLTK modules (keep only sentiment)
        "nltk.tokenize.stanford",
        "nltk.translate",
        "nltk.corpus.reader",
        "nltk.parse",
        "nltk.tag.stanford",
        "nltk.stem.snowball",
        # Exclude unused scientific visualization
        "seaborn",
        "plotly",
        "bokeh",
        # Exclude XML/HTML parsers we don't use
        "xml.etree.cElementTree",
        "lxml.html",
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
    strip=True,  # Enable binary stripping to reduce size
    upx=True,
    upx_exclude=[
        # Exclude files that shouldn't be compressed or cause issues with UPX
        "vcruntime140.dll",
        "python*.dll",
        "Qt*.dll",
    ],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join(basedir, "images", "YSocial_ico.png"),
)
