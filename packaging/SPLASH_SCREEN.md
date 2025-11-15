# Splash Screen Implementation - Platform-Specific Solution

## Overview

This implementation provides splash screens for YSocial with platform-specific solutions:

- **Windows**: PyInstaller's built-in Splash feature
- **Linux**: PyInstaller's built-in Splash feature  
- **macOS**: Custom Swift-based launcher (PyInstaller Splash not supported on macOS)

## Technical Details

### Windows & Linux

Uses PyInstaller's native Splash functionality:
- Configured in `y_social.spec`
- Automatically displays on app startup
- Closed programmatically via `pyi_splash.close()` after heavy imports
- Simple, reliable, and standard approach

### macOS

Uses a custom Swift launcher application:
- Located in `packaging/macos_launcher/`
- Displays a native macOS window with YSocial logo
- Launches the main PyInstaller application
- Automatically closes after ~5 seconds
- Integrated into the .app bundle via `create_dmg.sh`

## Build Process

### Windows/Linux

```bash
pyinstaller y_social.spec
```

The spec file automatically includes the splash screen.

### macOS

```bash
./packaging/build_and_package_macos.sh
```

This script:
1. Builds the Swift launcher (`macos_launcher/YSocialLauncher`)
2. Builds the PyInstaller executable
3. Signs the executable
4. Creates a DMG with the launcher integrated into the .app bundle

## File Structure

```
YSocial.app/
├── Contents/
│   ├── Info.plist         # Points to YSocialLauncher as executable
│   ├── MacOS/
│   │   ├── YSocialLauncher  # Swift launcher (shows splash)
│   │   └── YSocial          # Actual PyInstaller app
│   └── Resources/
│       ├── YSocial.png      # Logo for splash screen
│       └── YSocial.icns     # App icon
```

## How It Works (macOS)

1. User double-clicks YSocial.app
2. macOS launches `YSocialLauncher` (CFBundleExecutable in Info.plist)
3. Launcher displays splash window with YSocial logo
4. Launcher starts `YSocial` executable as a subprocess
5. After 5 seconds, launcher closes splash and quits
6. YSocial continues running independently

## Maintenance

### Updating the Splash Image

**Windows/Linux**: Update `images/YSocial.png`

**macOS**: Update `images/YSocial.png` (automatically copied to .app bundle)

### Modifying Splash Timing

**Windows/Linux**: Adjust `close_splash_screen()` call location in `y_web/pyinstaller_utils/y_social_launcher.py`

**macOS**: Modify the `DispatchQueue.main.asyncAfter(deadline: .now() + 5.0)` duration in `packaging/macos_launcher/YSocialLauncher.swift`

### Rebuilding the Swift Launcher

```bash
cd packaging/macos_launcher
./build_launcher.sh
```

Or it's automatically built by `build_and_package_macos.sh`.

## Testing

### Windows/Linux

Build and run:
```bash
pyinstaller y_social.spec --clean
./dist/YSocial
```

You should see the splash screen with "Loading YSocial..." text.

### macOS

Build DMG and test:
```bash
./packaging/build_and_package_macos.sh
open dist/YSocial-*.dmg
```

Mount the DMG, drag YSocial to Applications, and launch. You should see a splash window before the app starts.

## Troubleshooting

### "Splash screen is not supported on macOS"

This error occurs when trying to use PyInstaller's Splash on macOS. The spec file now handles this by conditionally disabling Splash on macOS and using the Swift launcher instead.

### Swift launcher not building

Ensure Xcode command-line tools are installed:
```bash
xcode-select --install
```

### Launcher not appearing in .app bundle

Check that:
1. `packaging/macos_launcher/YSocialLauncher` exists after build
2. `create_dmg.sh` successfully copies it to the bundle
3. `Info.plist` has `CFBundleExecutable` set to `YSocialLauncher`
