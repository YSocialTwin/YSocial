"""
PyInstaller hook for y_web package.

This hook ensures all necessary data files from the y_web package
are included in the PyInstaller bundle.
"""

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

# Collect all data files from y_web
datas = collect_data_files("y_web")

# Collect all submodules
hiddenimports = collect_submodules("y_web")
