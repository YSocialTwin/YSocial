"""
PyInstaller hook for pywebview package.

This hook ensures all necessary data files and platform-specific
modules from pywebview are included in the PyInstaller bundle.
"""

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

# Collect all data files from pywebview
datas = collect_data_files("webview")

# Collect all submodules, especially platform-specific ones
hiddenimports = collect_submodules("webview")
hiddenimports += collect_submodules("webview.platforms")

# Ensure platform-specific imports are included
# PyWebview uses different backends depending on the OS
hiddenimports += [
    "webview.platforms.qt",
    "webview.platforms.gtk",
    "webview.platforms.cocoa",
    "webview.platforms.winforms",
    "webview.platforms.mshtml",
    "webview.platforms.edgechromium",
    "webview.platforms.edgehtml",
]
