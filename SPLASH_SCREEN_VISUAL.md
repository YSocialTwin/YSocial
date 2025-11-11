# YSocial Splash Screen - Visual Description

## Layout Overview

```
┌─────────────────────────────────────────────────────────────┐
│                          WINDOW                             │
│              600x500px, Centered on Screen                  │
│         Dark Background (#1a1a2e)                           │
│         Blue Border (#0d95e8)                               │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│                    ╔════════════════╗                       │
│                    ║                ║                       │
│                    ║   YSOCIAL      ║                       │
│                    ║     LOGO       ║                       │
│                    ║   (200x200)    ║                       │
│                    ║                ║                       │
│                    ╚════════════════╝                       │
│                                                             │
│                   ┌──────────────┐                          │
│                   │ ROBOT IMAGE  │                          │
│                   │  (120x80)    │                          │
│                   └──────────────┘                          │
│                                                             │
│           Social Media Digital Twin                         │
│              (Bold, White, 14pt)                            │
│                                                             │
│         LLM-Powered Social Simulations                      │
│              (Gray, 10pt)                                   │
│                                                             │
│ ─────────────────────────────────────────────────────────  │
│                                                             │
│                    Created by:                              │
│                   (Blue, Bold, 9pt)                         │
│                                                             │
│        Rossetti, Stella, Cazabet, Abramski, Cau,           │
│      Citraro, Failla, Improta, Morini, Pansanella          │
│                  (Light Gray, 8pt)                          │
│                                                             │
│                   Release 2024                              │
│                   (Blue, Bold, 9pt)                         │
│                                                             │
│ ─────────────────────────────────────────────────────────  │
│                                                             │
│              Initializing YSocial...                        │
│                  (White, 9pt)                               │
│                                                             │
│     ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓░░░░░░░░░░░░░░░░░░░░                 │
│     (Animated Progress Bar - Blue Gradient)                │
│              (400px width)                                  │
│                                                             │
│                  GPL v3 License                             │
│                  (Dark Gray, 8pt)                           │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

## Color Scheme

- **Background**: `#1a1a2e` (Dark Navy)
- **Border**: `#0d95e8` (YSocial Blue)
- **Primary Text**: `#ffffff` (White)
- **Secondary Text**: `#a0a0a0` (Light Gray)
- **Accent Text**: `#0d95e8` (YSocial Blue)
- **Tertiary Text**: `#666666` (Dark Gray)
- **Progress Bar Background**: `#2a2a3e` (Slightly Lighter Navy)
- **Progress Bar Fill**: `#0d95e8` (YSocial Blue)

## Typography

- **Title (Social Media Digital Twin)**: Helvetica, 14pt, Bold, White
- **Subtitle (LLM-Powered...)**: Helvetica, 10pt, Regular, Gray
- **Section Headers (Created by, Release)**: Helvetica, 9pt, Bold, Blue
- **Author Names**: Helvetica, 8pt, Regular, Light Gray
- **Status Message**: Helvetica, 9pt, Regular, White
- **License Info**: Helvetica, 8pt, Regular, Dark Gray

## Animations

1. **Progress Bar**: 
   - Indeterminate animation (moving stripes)
   - Smooth left-to-right motion
   - Speed: 10ms interval
   - Gradient fill from left to right

2. **Status Updates**:
   - Text changes smoothly
   - No fade effects (instant text replacement)
   - Updates approximately every 0.5-1 seconds during initialization

## Behavior

1. **Appearance**:
   - Appears immediately when PyInstaller executable launches
   - Centered on screen
   - No window decorations (title bar, close button)
   - Always on top

2. **Status Messages** (in sequence):
   - "Initializing YSocial..."
   - "Loading application modules..."
   - "Initializing desktop mode..." (or "browser mode")
   - "Starting YSocial Desktop..." (or "Starting Flask server...")

3. **Duration**:
   - Minimum: 5 seconds
   - Actual: Until main application window is ready
   - Closes gracefully before main window appears

4. **Interaction**:
   - No user interaction required or possible
   - Cannot be closed by user
   - Automatically closes when initialization complete

## Example Screenshots

Since we can't generate actual screenshots in this environment, here's what users will see:

### Initial State
```
The splash screen appears with the YSocial logo at the top, followed by the 
robot image. Below that, "Social Media Digital Twin" appears in bold white 
text. The status shows "Initializing YSocial..." with an animated progress bar.
```

### During Loading
```
The progress bar continues animating, and the status text updates to show:
- "Loading application modules..."
- "Initializing desktop mode..."
- "Starting YSocial Desktop..."

Each message appears for approximately 1 second before the next update.
```

### Before Close
```
The final message "Starting YSocial Desktop..." appears briefly, then the 
splash screen fades out as the main application window appears.
```

## Technical Notes

- Window is frameless (no title bar or buttons)
- Uses tkinter's `overrideredirect(True)` for borderless window
- Progress bar uses ttk.Progressbar in indeterminate mode
- Images loaded using PIL/Pillow with LANCZOS resampling for quality
- Centered using screen dimensions via `winfo_screenwidth()` and `winfo_screenheight()`
- Runs in separate thread to avoid blocking main application startup
- Updates are thread-safe via tkinter's main thread execution

## Accessibility

- High contrast colors (white text on dark background)
- Clear, readable fonts
- No critical information that requires user action
- Informational only (status updates are optional)
- Short duration to minimize wait time

## Platform Compatibility

- **Windows**: Full support with native look
- **macOS**: Full support with native look
- **Linux**: Full support (requires tkinter system package)

All platforms show the same visual design with their native tkinter rendering.
