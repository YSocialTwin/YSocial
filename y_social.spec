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
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

# Get the base directory
basedir = os.path.abspath(SPECPATH)

# Collect all submodules for key packages
hidden_imports = [
    'nltk',
    'nltk.data',
    'sqlalchemy.sql.default_comparator',
    'sqlalchemy.ext.baked',
    'flask',
    'flask_login',
    'flask_sqlalchemy',
    'flask_wtf',
    'wtforms',
    'bs4',
    'feedparser',
    'requests',
    'werkzeug',
    'jinja2',
    'markupsafe',
    'cryptography',
    'openai',
    'ollama',
    'pyautogen',
    'perspective',
    'networkx',
    'numpy',
    'pillow',
    'psutil',
    'ysights',
    'jupyterlab',
    'gunicorn',
    'gevent',
    'psycopg2',
    'sqlalchemy_utils',
    'email_validator',
    'faker',
    'colorama',
    'tqdm',
    'pygments',
]

# Collect all submodules for important packages
hidden_imports += collect_submodules('flask')
hidden_imports += collect_submodules('flask_login')
hidden_imports += collect_submodules('flask_sqlalchemy')
hidden_imports += collect_submodules('sqlalchemy')
hidden_imports += collect_submodules('wtforms')
hidden_imports += collect_submodules('nltk')
hidden_imports += collect_submodules('bs4')
hidden_imports += collect_submodules('openai')
hidden_imports += collect_submodules('pyautogen')
hidden_imports += collect_submodules('ysights')

# Data files to include
datas = []

# Add NLTK data
datas += collect_data_files('nltk')

# Add y_web package data files
datas += [
    (os.path.join(basedir, 'y_web', 'static'), 'y_web/static'),
    (os.path.join(basedir, 'y_web', 'templates'), 'y_web/templates'),
    (os.path.join(basedir, 'data_schema'), 'data_schema'),
    (os.path.join(basedir, 'config_files'), 'config_files'),
]

# Add database schema directory
if os.path.exists(os.path.join(basedir, 'y_web', 'db')):
    datas += [(os.path.join(basedir, 'y_web', 'db'), 'y_web/db')]

# Add external submodules if they exist
for submodule in ['YServer', 'YClient']:
    submodule_path = os.path.join(basedir, 'external', submodule)
    if os.path.exists(submodule_path) and os.listdir(submodule_path):
        datas += [(submodule_path, f'external/{submodule}')]

a = Analysis(
    ['y_social_launcher.py'],
    pathex=[basedir],
    binaries=[],
    datas=datas,
    hiddenimports=hidden_imports,
    hookspath=[os.path.join(basedir, 'pyinstaller_hooks')],
    hooksconfig={},
    runtime_hooks=[os.path.join(basedir, 'pyinstaller_hooks', 'runtime_hook_nltk.py')],
    excludes=[
        'matplotlib',
        'pandas',
        'scipy',
        'pytest',
        'IPython',
        'notebook',
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
    [],
    exclude_binaries=True,
    name='YSocial',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='YSocial',
)
