# YSocial macOS DMG Packaging

This directory contains scripts and instructions for creating a macOS .dmg installer for YSocial with a custom background image and drag-to-Applications functionality.

## Overview

The DMG packaging scripts transform the PyInstaller-built YSocial executable into a professional macOS disk image installer featuring:

- **Custom background image** (using the YSocial splash screen)
- **Drag-to-Applications** shortcut for easy installation
- **Professional .app bundle** with proper macOS metadata
- **Custom icon** throughout the installer
- **Uninstall script** for complete removal
- **User README** with comprehensive usage instructions
- **Compressed DMG** for efficient distribution

## Files in This Directory

- **`create_dmg.sh`** - Main DMG creation script (no external dependencies)
- **`create_dmg_simple.sh`** - Alternative using create-dmg tool
- **`uninstall_ysocial.py`** - Platform-independent uninstaller (Python)
- **`uninstall.sh`** - Shell wrapper for the uninstaller
- **`README_USER.md`** - User-facing documentation included in DMG
- **`README.md`** (this file) - Developer documentation

## Prerequisites

### Required
- **macOS** (10.13 or later recommended)
- **Xcode Command Line Tools**: `xcode-select --install`
- **YSocial executable** built with PyInstaller (see [BUILD_EXECUTABLES.md](../BUILD_EXECUTABLES.md))

### Optional (for simpler workflow)
- **Homebrew**: `/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"`
- **create-dmg tool**: `brew install create-dmg` (for `create_dmg_simple.sh`)

## Scripts

### 1. `create_dmg.sh` (Recommended - No external dependencies)

The main DMG creation script that uses only built-in macOS tools.

**Advantages:**
- No external dependencies required
- Works on any macOS system with Xcode tools
- Full control over DMG appearance and layout
- Includes detailed progress output

**Usage:**
```bash
cd /path/to/YSocial
./packaging/create_dmg.sh
```

**With custom version:**
```bash
VERSION=1.2.3 ./packaging/create_dmg.sh
```

### 2. `create_dmg_simple.sh` (Alternative - Requires create-dmg)

A simpler script using the `create-dmg` tool for easier customization.

**Advantages:**
- Simpler syntax
- Easier to customize
- Less code to maintain

**Disadvantages:**
- Requires `create-dmg` tool to be installed
- Additional dependency

**Installation:**
```bash
brew install create-dmg
```

**Usage:**
```bash
cd /path/to/YSocial
./packaging/create_dmg_simple.sh
```

## Complete Build Process

### Step 1: Build the YSocial Executable

First, build the YSocial executable using PyInstaller:

```bash
# Navigate to project root
cd /path/to/YSocial

# Ensure dependencies are installed
pip install -r requirements.txt
pip install pyinstaller

# Initialize git submodules if not already done
git submodule update --init --recursive

# Build the executable
pyinstaller y_social.spec --clean --noconfirm
```

This will create the executable at `dist/YSocial`.

### Step 2: Create the DMG

Once the executable is built, create the DMG installer:

```bash
# Using the main script (recommended)
./packaging/create_dmg.sh

# OR using the simple script (requires create-dmg)
./packaging/create_dmg_simple.sh
```

The DMG will be created at `dist/YSocial-1.0.0.dmg` (or with your specified version).

### Step 3: Test the DMG

Mount and test the DMG before distribution:

```bash
# Mount the DMG
open dist/YSocial-1.0.0.dmg

# The DMG window should show:
# - YSocial.app icon (center left)
# - Applications folder shortcut (center right)
# - README.md file (bottom left)
# - Uninstall YSocial.command (bottom right)
# - Custom background image with arrow
# - Drag YSocial.app to Applications to install
```

### Step 4: Distribute

The DMG file is now ready for distribution! You can:
- Upload it to your website
- Attach it to a GitHub release
- Share it via download links
- Include it in documentation

## DMG Contents

When users open the DMG, they will find:

1. **YSocial.app** - The main application (drag to Applications)
2. **Applications** - Symlink to /Applications folder (drag target)
3. **README.md** - User documentation with:
   - Installation instructions
   - All command-line flags and options
   - Where data is stored
   - Uninstall instructions
   - Troubleshooting guide
4. **Uninstall YSocial.command** - Uninstaller script (double-click to run)
5. **Background image** - Custom YSocial splash screen with arrow

## Uninstaller

The DMG includes a comprehensive uninstaller that:

- **Platform-independent**: Written in Python, works on macOS, Linux, Windows
- **Safe**: Shows what will be deleted before proceeding
- **Thorough**: Finds and removes:
  - YSocial.app from /Applications
  - All data directories (y_web/, db/, logs/, etc.)
  - Configuration files
  - User-created experiment data
- **Interactive**: Asks for confirmation before deletion
- **Size reporting**: Shows how much disk space will be freed

### Using the Uninstaller

From the DMG:
```bash
# Double-click "Uninstall YSocial.command" in the DMG
# Or from Terminal:
./uninstall.sh
```

The uninstaller will:
1. Scan for YSocial installations
2. Show what will be deleted and total size
3. Ask for confirmation (type 'yes' to proceed)
4. Remove all YSocial files
5. Report results

**Note:** May require sudo for system-level installations.

## What the Scripts Do

### Bundle Creation

1. **Creates a proper .app bundle structure:**
   ```
   YSocial.app/
   ├── Contents/
   │   ├── Info.plist          # macOS bundle metadata
   │   ├── MacOS/
   │   │   └── YSocial         # Executable
   │   └── Resources/
   │       └── YSocial.icns    # Application icon
   ```

2. **Generates Info.plist** with proper bundle identifiers:
   - Bundle ID: `com.ysocialtwin.ysocial`
   - Display Name: `YSocial`
   - Version info
   - High-resolution support
   - Minimum macOS version

3. **Converts PNG icon to .icns format:**
   - Multiple resolutions (16x16 to 512x512)
   - Retina display support (@2x variants)
   - Uses `sips` and `iconutil` built-in tools

### DMG Customization

1. **Custom Background:**
   - Uses `images/YSocial_v.png` (the splash screen image)
   - Placed in `.background/` folder (hidden from user)
   - Applied to DMG window via AppleScript

2. **Window Layout:**
   - Window size: 284x383 pixels (matches background image exactly)
   - Icon view with 48px icons (compact, clean design)
   - Additional files (README, Uninstaller) shown at bottom
   - YSocial.app positioned on middle left (x=50, y=160)
   - Applications symlink on middle right (x=210, y=160)
   - README.md at bottom left (x=70, y=310)
   - Uninstall script at bottom right (x=190, y=310)
   - Icons aligned with arrow graphic in background image
   - Window dimensions exactly match background image (no scaling)
   - Clean, professional appearance

3. **Visual Polish:**
   - Custom volume icon
   - Hidden toolbar and status bar
   - Custom window bounds
   - Arranged icons for drag-and-drop

## Customization

### Change Version

Set the `VERSION` environment variable:

```bash
VERSION=2.0.0 ./packaging/create_dmg.sh
```

### Change Background Image

Edit the script and modify the `BACKGROUND_IMAGE` variable:

```bash
BACKGROUND_IMAGE="path/to/your/background.png"
```

### Change Window Size

In `create_dmg.sh`, modify the AppleScript bounds:

```applescript
set the bounds of container window to {400, 100, 684, 483}
# Format: {left, top, right, bottom}
# Current: 284x383 window (exact background image size)
```

### Change Icon Positions

In `create_dmg.sh`, modify the icon positions:

```applescript
set position of item "YSocial.app" of container window to {50, 160}
set position of item "Applications" of container window to {210, 160}
# Format: {x, y} from top-left
# Current positions are centered to align with arrow in background
```

### Change Icon Size

In `create_dmg.sh`, modify the icon size:

```applescript
set icon size of viewOptions to 48
# Values: 16, 32, 48, 64, 72, 128, 256
# Current: 48 (compact size optimized for small window)
```

## Troubleshooting

### "YSocial executable not found"

**Problem:** The script can't find the built executable.

**Solution:**
```bash
# Build the executable first
pyinstaller y_social.spec --clean --noconfirm

# Verify it exists
ls -lh dist/YSocial
```

### "This script must be run on macOS"

**Problem:** Trying to create DMG on non-macOS system.

**Solution:** DMG creation requires macOS. Options:
1. Use a Mac for packaging
2. Use GitHub Actions (see CI/CD section)
3. Use a macOS VM

### "create-dmg is not installed" (for simple script)

**Problem:** The `create-dmg` tool is not installed.

**Solution:**
```bash
brew install create-dmg
```

Or use `create_dmg.sh` instead (no external dependencies).

### "Resource busy" or "couldn't unmount"

**Problem:** DMG is still mounted from previous run.

**Solution:**
```bash
# Force unmount all YSocial volumes
hdiutil detach /Volumes/YSocial -force

# Then retry
./packaging/create_dmg.sh
```

### AppleScript permissions

**Problem:** macOS blocks AppleScript from controlling Finder.

**Solution:**
1. Go to System Preferences → Security & Privacy → Privacy
2. Select "Automation" in left sidebar
3. Enable Terminal (or your script runner) to control Finder
4. Retry the script

### Background image not showing

**Problem:** Custom background doesn't appear in DMG.

**Solution:**
1. Verify image exists: `ls -lh images/YSocial_v.png`
2. Check image format (PNG recommended)
3. Try opening DMG and manually setting background as test
4. Ensure `.background` folder permissions are correct

## CI/CD Integration

### GitHub Actions

You can integrate DMG creation into your GitHub Actions workflow:

```yaml
name: Build DMG

on:
  push:
    tags:
      - 'v*'

jobs:
  build-dmg:
    runs-on: macos-latest
    steps:
      - uses: actions/checkout@v3
        with:
          submodules: recursive
      
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      
      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install pyinstaller
      
      - name: Build executable
        run: pyinstaller y_social.spec --clean --noconfirm
      
      - name: Create DMG
        run: ./packaging/create_dmg.sh
      
      - name: Upload DMG
        uses: actions/upload-artifact@v3
        with:
          name: YSocial-macOS-DMG
          path: dist/*.dmg
```

### Manual Release Process

1. **Build executable:**
   ```bash
   pyinstaller y_social.spec --clean --noconfirm
   ```

2. **Create DMG:**
   ```bash
   VERSION=$(git describe --tags --abbrev=0) ./packaging/create_dmg.sh
   ```

3. **Upload to GitHub release:**
   ```bash
   gh release upload v1.0.0 dist/YSocial-1.0.0.dmg
   ```

## Technical Details

### Why Create a .app Bundle?

macOS users expect applications to be in `.app` bundle format because:
- Double-clickable from Finder
- Proper integration with Dock and Launchpad
- Correct icon display in Finder
- Standard macOS application behavior
- Can be signed and notarized for distribution

### DMG Format

The scripts create compressed DMG files using:
- **Format:** UDZO (compressed, read-only)
- **Compression:** zlib level 9 (maximum compression)
- **Filesystem:** HFS+ (compatible with older macOS versions)

### Size Optimization

The scripts automatically:
1. Calculate required DMG size based on app bundle size
2. Add 100MB padding for metadata and background
3. Compress the final DMG to reduce file size by ~40-60%

## Background Image Details

The DMG uses the YSocial splash screen image (`images/YSocial_v.png`), which features:
- YSocial logo
- Robot illustration
- Author credits
- Modern dark theme design
- Professional appearance

This provides visual continuity between the installation experience and the application itself.

## Best Practices

### Before Distribution

1. **Test the DMG:**
   - Mount it on a clean macOS system
   - Drag to Applications
   - Launch the app
   - Verify all functionality works

2. **Code Signing (recommended for distribution):**
   ```bash
   # Sign the app bundle before creating DMG
   codesign --force --deep --sign "Developer ID Application: Your Name" \
            dmg_staging/YSocial.app
   ```

3. **Notarization (required for macOS 10.15+):**
   - Submit to Apple for notarization
   - Staple the ticket to the DMG
   - See Apple's notarization documentation

### Version Management

Always update the version in:
1. **VERSION environment variable** when running scripts
2. **Info.plist** (automatically handled by scripts)
3. **Git tags** for release tracking

Example:
```bash
git tag -a v1.2.3 -m "Release version 1.2.3"
VERSION=1.2.3 ./packaging/create_dmg.sh
```

## Additional Resources

- [Apple's Bundle Programming Guide](https://developer.apple.com/library/archive/documentation/CoreFoundation/Conceptual/CFBundles/)
- [DMG Canvas](https://www.araelium.com/dmgcanvas) - GUI tool for DMG creation
- [create-dmg GitHub](https://github.com/create-dmg/create-dmg)
- [PyInstaller Documentation](https://pyinstaller.org/)

## License

These packaging scripts follow the same GPL v3 license as YSocial.

## Support

For issues related to DMG creation:
1. Check the troubleshooting section above
2. Verify you're on macOS with Xcode tools installed
3. Ensure the executable was built successfully first
4. Open an issue on the YSocial GitHub repository

## Changelog

### Version 1.0.0
- Initial DMG packaging scripts
- Custom background using splash screen image
- Drag-to-Applications functionality
- Automatic .app bundle creation
- Icon conversion and integration
- Two script options (full and simple)
