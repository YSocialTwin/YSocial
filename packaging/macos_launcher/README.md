# YSocial macOS Launcher

This directory contains the Swift-based launcher for YSocial on macOS.

## Purpose

PyInstaller's built-in splash screen feature is not supported on macOS. This launcher provides an alternative splash screen solution for macOS builds.

## How It Works

1. The launcher displays a splash window with the YSocial logo
2. It then launches the actual YSocial PyInstaller application
3. After a few seconds (or when YSocial signals ready), the splash closes
4. The launcher quits, leaving YSocial running

## Building

Run the build script:

```bash
./build_launcher.sh
```

This compiles the Swift code into an executable that will be integrated into the macOS .app bundle.

## Integration

The `build_and_package_macos.sh` script automatically:
1. Builds the Swift launcher
2. Places it in the .app bundle alongside the PyInstaller executable
3. Configures the .app to launch via the launcher instead of directly

## File Structure

- `YSocialLauncher.swift` - Main Swift source code
- `build_launcher.sh` - Build script
- `README.md` - This file
