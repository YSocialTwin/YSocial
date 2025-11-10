# YSocial Splash Screen

## Overview

A dynamic and sleek splash screen has been added for PyInstaller builds of YSocial. The splash screen displays:

- **YSocial Logo** (`images/YSocial_v.png`)
- **Robot Image** from the admin dashboard (`y_web/static/assets/img/robots/header3.jpg`)
- **Authors**: Rossetti, Stella, Cazabet, Abramski, Cau, Citraro, Failla, Improta, Morini, Pansanella
- **Release Year**: 2024
- **Real-time status updates** during application initialization
- **Animated progress bar** with modern styling

## Features

### Visual Design
- **Dark Theme**: Modern dark background (#1a1a2e) with bright accent colors
- **Accent Color**: YSocial blue (#0d95e8) for highlights and text
- **Professional Layout**: Centered window with clean typography
- **Smooth Animations**: Indeterminate progress bar with custom styling
- **Responsive**: Window centered on any screen size (600x500 pixels)

### Functionality
- **Automatic Detection**: Only shows when running as PyInstaller executable
- **Status Updates**: Real-time messages during initialization:
  - "Loading application modules..."
  - "Initializing desktop/browser mode..."
  - "Starting YSocial Desktop/Flask server..."
- **Graceful Closure**: Automatically closes before main application window appears
- **Error Handling**: Fails gracefully if images can't be loaded or GUI unavailable

## Implementation Details

### Files Modified

1. **`splash_screen.py`** (NEW)
   - Main splash screen implementation using tkinter
   - `YSocialSplashScreen` class with modern UI
   - `show_splash_screen()` helper function for easy integration
   - Resource path resolution for PyInstaller compatibility

2. **`y_social_launcher.py`** (MODIFIED)
   - Added `is_pyinstaller()` detection function
   - Integrated splash screen for both desktop and browser modes
   - Status updates at key initialization points
   - Proper cleanup before showing main application

3. **`y_social.spec`** (MODIFIED)
   - Added `images/` directory to bundled data
   - Added `splash_screen.py` to bundled modules
   - Ensures all splash screen assets are included in executable

### Technical Details

#### PyInstaller Integration
The splash screen uses `sys._MEIPASS` to locate bundled resources:

```python
def _get_resource_path(self, relative_path):
    try:
        base_path = sys._MEIPASS  # PyInstaller temp folder
    except AttributeError:
        base_path = os.path.abspath(".")  # Development environment
    return os.path.join(base_path, relative_path)
```

#### Threading Model
The splash screen runs in a separate thread to avoid blocking:
- Main thread: Continues with application initialization
- Splash thread: Displays GUI and handles events
- Communication: Status updates via thread-safe method calls

#### Timing
- **Minimum Duration**: 5 seconds (configurable)
- **Automatic Closure**: Closes when `splash.close()` is called
- **Delayed Closure**: 1 second delay before close to show final status

## Usage

### For End Users
The splash screen appears automatically when launching the YSocial PyInstaller executable. No user action is required.

### For Developers

#### Building with PyInstaller
```bash
pyinstaller y_social.spec
```

The splash screen will be automatically included in the build.

#### Testing Locally
The splash screen only appears in PyInstaller builds. To test:

```bash
# Build the executable
pyinstaller y_social.spec

# Run the executable
./dist/YSocial
```

#### Customizing the Splash Screen

**Change Colors:**
Edit `splash_screen.py` and modify the color constants:
```python
bg="#1a1a2e"           # Background color
fg="#0d95e8"           # Accent/highlight color
text_color="#ffffff"   # Primary text color
secondary_color="#a0a0a0"  # Secondary text color
```

**Change Duration:**
Edit `y_social_launcher.py`:
```python
splash_screen.show(duration=5)  # Change from 5 to desired seconds
```

**Add Status Messages:**
Add more status updates in `y_social_launcher.py`:
```python
if splash_screen:
    splash_screen.update_status("Your custom message...")
```

## Design Rationale

### Why tkinter?
- **Built-in**: No additional dependencies required
- **Lightweight**: Small footprint for splash screen
- **Cross-platform**: Works on Windows, macOS, and Linux
- **PyInstaller Compatible**: Well-supported by PyInstaller

### Why Only for PyInstaller?
- **Development Flexibility**: Developers don't need splash screen delays
- **Fast Iteration**: Splash screen only shown in production builds
- **Clean Separation**: Development vs. production user experience

## Troubleshooting

### Splash Screen Doesn't Appear
1. **Check PyInstaller Build**: Ensure you're running the PyInstaller executable, not the Python script
2. **Verify Images**: Confirm `images/YSocial_v.png` and `y_web/static/assets/img/robots/header3.jpg` exist
3. **Check Console**: Look for error messages like "Could not show splash screen: ..."

### Splash Screen Doesn't Close
- This should not happen as the splash screen auto-closes
- If it persists, check that `splash_screen.close()` is being called in the launcher

### Images Don't Load
- The splash screen will still work with text-only fallback
- Check that images are included in PyInstaller build by examining `y_social.spec`

## Future Enhancements

Possible improvements:
- Add version number to splash screen
- Include progress percentage for specific initialization steps
- Add fade-in/fade-out effects
- Support for custom themes
- Localization support for different languages

## License

The splash screen follows the same GPL v3 license as YSocial.
