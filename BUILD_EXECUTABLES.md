# Building YSocial Executables

This document describes how to build standalone executables for YSocial using PyInstaller.

## Automated Builds (GitHub Actions)

The repository includes a GitHub Actions workflow that automatically builds executables for Windows, macOS, and Linux.

### Triggering Builds

The workflow can be triggered in three ways:

1. **Manual trigger**: Go to Actions → Build Executables → Run workflow
2. **Git tags**: Push a tag starting with `v` (e.g., `v1.0.0`)
3. **Releases**: Create a new release on GitHub

### Artifacts

Build artifacts are available for 90 days after the workflow completes:
- `YSocial-linux.tar.gz` - Linux executable
- `YSocial-macos.tar.gz` - macOS executable  
- `YSocial-windows.zip` - Windows executable

For releases, these artifacts are automatically attached to the release.

## Manual Local Build

To build executables locally for testing:

### Prerequisites

1. Python 3.11 (recommended)
2. All dependencies from `requirements.txt`
3. PyInstaller: `pip install pyinstaller`
4. Git submodules initialized: `git submodule update --init --recursive`

### Build Steps

```bash
# 1. Clone repository with submodules
git clone --recursive https://github.com/YSocialTwin/YSocial.git
cd YSocial

# 2. Create and activate virtual environment (recommended)
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt
pip install pyinstaller

# 4. Download NLTK data
python -c "import nltk; nltk.download('vader_lexicon')"

# 5. Create config directory if missing
mkdir -p config_files

# 6. Build with PyInstaller
pyinstaller y_social.spec --clean --noconfirm
```

### Build Output

The executable will be located in `dist/YSocial/`:
- Linux/macOS: `dist/YSocial/YSocial`
- Windows: `dist/YSocial/YSocial.exe`

### Testing the Executable

```bash
# Linux/macOS
cd dist/YSocial
./YSocial --help
./YSocial                    # Launches in desktop mode (default)

# Try browser mode instead
./YSocial --browser

# Windows
cd dist\YSocial
YSocial.exe --help
YSocial.exe                  # Launches in desktop mode (default)

# Try browser mode instead
YSocial.exe --browser
```

The application now **launches in desktop mode by default** with a native window. Use `--browser` flag to open in a web browser instead.

## Desktop Mode (Default)

**Desktop mode is now the default!** YSocial uses PyWebview to provide a native window experience without browser chrome:

```bash
# Start normally (desktop mode is default)
./YSocial

# Customize window size
./YSocial --window-width 1600 --window-height 900

# Switch to browser mode if needed
./YSocial --browser
```

**Desktop mode features:**
- Native window without browser UI/chrome
- Integrated window controls (minimize, maximize, close)
- Better desktop integration
- Confirmation dialog on window close
- Resizable window with minimum size constraints

**Note:** Desktop mode requires a GUI environment. On Linux, it may require additional system packages depending on the backend used (GTK, Qt, etc.).

## Build Configuration Files

### `y_social.spec`
PyInstaller specification file that defines:
- Entry point (`y_social_launcher.py`)
- Data files to include (templates, static files, schemas)
- Hidden imports for dynamic dependencies
- Build options and exclusions

### `y_social_launcher.py`
Wrapper script that:
- Provides a clean command-line interface
- Supports both browser mode (default) and desktop mode (`--desktop`)
- Auto-opens browser/desktop window when server is ready
- Handles graceful shutdown
- Works with PyInstaller's bundled environment

### `y_social_desktop.py`
Desktop mode module that:
- Uses PyWebview to create native desktop windows
- Runs Flask server in background thread
- Provides desktop app experience without browser chrome
- Can be used standalone or via launcher

### `pyinstaller_hooks/`
Custom PyInstaller hooks:
- `hook-y_web.py`: Ensures y_web package data files are included
- `hook-webview.py`: Ensures pywebview platform-specific modules are included
- `runtime_hook_nltk.py`: Configures NLTK data paths at runtime

## Troubleshooting

### Build Fails with Import Errors
- Ensure all dependencies are installed: `pip install -r requirements.txt`
- Check that submodules are initialized: `git submodule status`

### Executable Fails to Start
- Check console output for error messages
- Verify NLTK data was downloaded during build
- Ensure data files are present in `dist/YSocial/`

### Missing Templates or Static Files
- Check `y_social.spec` includes correct data paths
- Verify `pyinstaller_hooks/hook-y_web.py` is being used
- Rebuild with `--clean` flag

### Large Executable Size
The executable is large (~500MB-1GB) because it includes:
- Python interpreter
- All dependencies (Flask, SQLAlchemy, NLTK, scikit-learn, scipy, etc.)
- Static assets (CSS, JS, images)
- Database schemas
- Submodules (YServer, YClient)

This is normal for PyInstaller-built applications with many dependencies.

**Note**: Some large packages like matplotlib and pandas are excluded since they're not needed for the core application.

## Platform-Specific Notes

### Linux
- Executable is built for the same Linux distribution as the build machine
- May require additional system libraries on target machines
- Use Ubuntu-based systems for broadest compatibility

### macOS
- Unsigned executables will show security warnings
- Users need to right-click → Open, or allow in System Preferences
- Consider code signing for production releases

### Windows
- Antivirus may flag the executable (false positive)
- Add to antivirus exceptions if needed
- UPX compression is enabled to reduce size

## Distribution

When distributing executables:

1. Include the README.txt created by the build process
2. Test on clean machines without Python installed
3. Provide instructions for first-time users
4. Mention system requirements (RAM, disk space)
5. Include link to full documentation

## CI/CD Integration

The GitHub Actions workflow (`.github/workflows/build-executables.yml`) handles:
- Multi-platform builds (Linux, macOS, Windows)
- Dependency caching
- Artifact creation and upload
- Release asset attachment
- README generation

See the workflow file for details and customization options.
