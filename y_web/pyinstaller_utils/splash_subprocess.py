#!/usr/bin/env python
"""
Standalone Splash Screen Subprocess for YSocial.

This script runs as a separate process to display the splash screen
while the main application loads heavy dependencies. It can be terminated
by the parent process once loading is complete.

Usage:
    python splash_subprocess.py

The splash screen will display until the parent process terminates it.
"""

import os
import sys
import tkinter as tk
from tkinter import ttk

# Only import PIL if available, fallback to text-only splash if not
try:
    from PIL import Image, ImageTk

    HAS_PIL = True
except ImportError:
    HAS_PIL = False


def get_resource_path(relative_path):
    """
    Get absolute path to resource, works for dev and for PyInstaller.

    Args:
        relative_path: Relative path to the resource

    Returns:
        Absolute path to the resource
    """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except AttributeError:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)


def get_version():
    """
    Read version from VERSION file.

    Returns:
        Version string (e.g., "2.0.0")
    """
    try:
        version_path = get_resource_path("VERSION")
        with open(version_path, "r") as f:
            return f.read().strip()
    except Exception:
        return "2.0.0"  # Fallback version


class SplashSubprocess:
    """Lightweight splash screen for subprocess execution."""

    def __init__(self):
        """Initialize the splash screen with minimal dependencies."""
        self.root = tk.Tk()
        self.root.overrideredirect(True)  # Remove window decorations
        self.root.attributes("-topmost", True)  # Keep on top

        # Default dimensions
        self.logo_photo = None
        self.robot_photo = None
        robot_display_width = 700
        robot_display_height = 400
        left_column_width = 250

        # Try to load images if PIL is available
        if HAS_PIL:
            try:
                # Load robot image
                robot_path = get_resource_path(
                    "y_web/static/assets/img/robots/header3.jpg"
                )
                if os.path.exists(robot_path):
                    robot_img = Image.open(robot_path)
                    aspect_ratio = robot_img.width / robot_img.height
                    robot_display_width = int(robot_display_height * aspect_ratio)
                    robot_img = robot_img.resize(
                        (robot_display_width, robot_display_height),
                        Image.Resampling.LANCZOS,
                    )
                    self.robot_photo = ImageTk.PhotoImage(robot_img)
            except Exception:
                pass  # Silently fail, use defaults

            try:
                # Load logo
                logo_path = get_resource_path("images/YSocial_v.png")
                if os.path.exists(logo_path):
                    logo_img = Image.open(logo_path)
                    logo_target_width = 100
                    logo_aspect_ratio = logo_img.width / logo_img.height
                    logo_target_height = int(logo_target_width / logo_aspect_ratio)
                    logo_img = logo_img.resize(
                        (logo_target_width, logo_target_height),
                        Image.Resampling.LANCZOS,
                    )
                    self.logo_photo = ImageTk.PhotoImage(logo_img)
            except Exception:
                pass  # Silently fail, use defaults

        # Calculate window size
        window_width = left_column_width + robot_display_width + 20
        window_height = robot_display_height + 20

        # Center the window on screen
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        x = (screen_width - window_width) // 2
        y = (screen_height - window_height) // 2

        self.root.geometry(f"{window_width}x{window_height}+{x}+{y}")

        # Configure background
        self.main_frame = tk.Frame(
            self.root, bg="#1a1a2e", highlightthickness=2, highlightbackground="#0d95e8"
        )
        self.main_frame.pack(fill=tk.BOTH, expand=True, padx=0, pady=0)

        self._create_content()

    def _create_content(self):
        """Create the splash screen content."""
        # Create two-column layout
        content_frame = tk.Frame(self.main_frame, bg="#1a1a2e")
        content_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Left column - Logo and credits
        left_column = tk.Frame(content_frame, bg="#1a1a2e", width=250)
        left_column.pack(side=tk.LEFT, fill=tk.BOTH, padx=(0, 10))
        left_column.pack_propagate(False)

        # Logo at top of left column
        if self.logo_photo:
            logo_label = tk.Label(left_column, image=self.logo_photo, bg="#1a1a2e")
            logo_label.pack(pady=(10, 5))
        else:
            # Fallback text logo
            logo_label = tk.Label(
                left_column,
                text="YSocial",
                font=("Helvetica", 18, "bold"),
                fg="#0d95e8",
                bg="#1a1a2e",
            )
            logo_label.pack(pady=(10, 5))

        # Title
        title_label = tk.Label(
            left_column,
            text="Social Media\nDigital Twin",
            font=("Helvetica", 12, "bold"),
            fg="#ffffff",
            bg="#1a1a2e",
            justify=tk.CENTER,
        )
        title_label.pack(pady=(5, 3))

        # Subtitle
        subtitle_label = tk.Label(
            left_column,
            text="LLM-Powered\nSocial Simulations",
            font=("Helvetica", 9),
            fg="#a0a0a0",
            bg="#1a1a2e",
            justify=tk.CENTER,
        )
        subtitle_label.pack(pady=(0, 10))

        # Separator line
        separator = tk.Frame(left_column, bg="#0d95e8", height=2)
        separator.pack(fill=tk.X, padx=20, pady=8)

        # Authors section
        authors_title = tk.Label(
            left_column,
            text="Created by:",
            font=("Helvetica", 9, "bold"),
            fg="#0d95e8",
            bg="#1a1a2e",
        )
        authors_title.pack(pady=(10, 5))

        authors_label = tk.Label(
            left_column,
            text="Rossetti et al.",
            font=("Helvetica", 8),
            fg="#cccccc",
            bg="#1a1a2e",
            justify=tk.CENTER,
        )
        authors_label.pack(pady=(0, 10))

        # Release date with version
        version = get_version()
        release_label = tk.Label(
            left_column,
            text=f"v{version} (Nalthis) 11/2025",
            font=("Helvetica", 9, "bold"),
            fg="#0d95e8",
            bg="#1a1a2e",
        )
        release_label.pack(pady=(5, 10))

        # Loading indicator
        self.loading_label = tk.Label(
            left_column,
            text="Loading dependencies...",
            font=("Helvetica", 8),
            fg="#ffffff",
            bg="#1a1a2e",
        )
        self.loading_label.pack(side=tk.BOTTOM, pady=(0, 20))

        # Progress bar with animation
        style = ttk.Style()
        style.theme_use("default")
        style.configure(
            "Custom.Horizontal.TProgressbar",
            troughcolor="#2a2a3e",
            bordercolor="#0d95e8",
            background="#0d95e8",
            lightcolor="#0d95e8",
            darkcolor="#0d95e8",
        )

        self.progress = ttk.Progressbar(
            left_column,
            length=200,
            mode="indeterminate",
            style="Custom.Horizontal.TProgressbar",
        )
        self.progress.pack(side=tk.BOTTOM, pady=(0, 5))
        self.progress.start(10)

        # License at very bottom
        bottom_label = tk.Label(
            left_column,
            text="GPL v3",
            font=("Helvetica", 7),
            fg="#666666",
            bg="#1a1a2e",
        )
        bottom_label.pack(side=tk.BOTTOM, pady=(0, 5))

        # Right column - Robot image
        right_column = tk.Frame(content_frame, bg="#1a1a2e")
        right_column.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        if self.robot_photo:
            robot_label = tk.Label(right_column, image=self.robot_photo, bg="#1a1a2e")
            robot_label.pack(fill=tk.BOTH, expand=True)
        else:
            # Fallback emoji
            placeholder = tk.Label(
                right_column,
                text="🤖",
                font=("Helvetica", 48),
                fg="#0d95e8",
                bg="#1a1a2e",
            )
            placeholder.pack(fill=tk.BOTH, expand=True)

    def run(self):
        """Run the splash screen mainloop."""
        try:
            self.root.mainloop()
        except KeyboardInterrupt:
            pass


def main():
    """Main entry point for splash subprocess."""
    try:
        splash = SplashSubprocess()
        splash.run()
    except Exception as e:
        # Silently exit on any error - splash screen is non-critical
        print(f"Splash screen error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
