"""
Dynamic splash screen for YSocial PyInstaller application.

Displays the YSocial logo, robot image, author information, and release date
while the application initializes.
"""

import os
import sys
import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageTk
import threading
import time


class YSocialSplashScreen:
    """Modern splash screen for YSocial application."""

    def __init__(self):
        """Initialize the splash screen."""
        self.root = tk.Tk()
        self.root.overrideredirect(True)  # Remove window decorations
        self.root.attributes("-topmost", True)  # Keep on top

        # Load images first to determine dimensions
        self.logo_photo = None
        self.robot_photo = None
        robot_display_height = 400  # Target height for robot image

        # Load robot image to determine splash dimensions
        try:
            robot_path = self._get_resource_path(
                "y_web/static/assets/img/robots/header3.jpg"
            )
            robot_img = Image.open(robot_path)
            # Calculate dimensions preserving aspect ratio
            aspect_ratio = robot_img.width / robot_img.height
            robot_display_width = int(robot_display_height * aspect_ratio)
            robot_img = robot_img.resize(
                (robot_display_width, robot_display_height), Image.Resampling.LANCZOS
            )
            self.robot_photo = ImageTk.PhotoImage(robot_img)
        except Exception as e:
            print(f"Warning: Could not load robot image: {e}")
            robot_display_width = 700
            robot_display_height = 400

        # Load logo preserving aspect ratio
        try:
            logo_path = self._get_resource_path("images/YSocial_v.png")
            logo_img = Image.open(logo_path)
            # Calculate dimensions preserving aspect ratio (target width ~150px)
            logo_target_width = 150
            logo_aspect_ratio = logo_img.width / logo_img.height
            logo_target_height = int(logo_target_width / logo_aspect_ratio)
            logo_img = logo_img.resize(
                (logo_target_width, logo_target_height), Image.Resampling.LANCZOS
            )
            self.logo_photo = ImageTk.PhotoImage(logo_img)
        except Exception as e:
            print(f"Warning: Could not load logo: {e}")

        # Calculate window size based on robot image
        left_column_width = 250
        window_width = left_column_width + robot_display_width + 20  # 20px padding
        window_height = robot_display_height + 20  # 20px padding

        # Center the window on screen
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        x = (screen_width - window_width) // 2
        y = (screen_height - window_height) // 2

        self.root.geometry(f"{window_width}x{window_height}+{x}+{y}")

        # Configure background with gradient-like effect
        self.main_frame = tk.Frame(
            self.root, bg="#1a1a2e", highlightthickness=2, highlightbackground="#0d95e8"
        )
        self.main_frame.pack(fill=tk.BOTH, expand=True, padx=0, pady=0)

        self._create_content()

    def _get_resource_path(self, relative_path):
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

    def _create_content(self):
        """Create the splash screen content with two-column layout."""
        # Create two-column layout
        content_frame = tk.Frame(self.main_frame, bg="#1a1a2e")
        content_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Left column - Logo and credits
        left_column = tk.Frame(content_frame, bg="#1a1a2e", width=250)
        left_column.pack(side=tk.LEFT, fill=tk.BOTH, padx=(0, 10))
        left_column.pack_propagate(False)  # Maintain fixed width

        # Logo at top of left column
        if self.logo_photo:
            logo_label = tk.Label(left_column, image=self.logo_photo, bg="#1a1a2e")
            logo_label.pack(pady=(20, 10))
        else:
            # Fallback if logo can't be loaded
            logo_label = tk.Label(
                left_column,
                text="YSocial",
                font=("Helvetica", 24, "bold"),
                fg="#0d95e8",
                bg="#1a1a2e",
            )
            logo_label.pack(pady=(20, 10))

        # Title
        title_label = tk.Label(
            left_column,
            text="Social Media\nDigital Twin",
            font=("Helvetica", 12, "bold"),
            fg="#ffffff",
            bg="#1a1a2e",
            justify=tk.CENTER,
        )
        title_label.pack(pady=(10, 5))

        # Subtitle
        subtitle_label = tk.Label(
            left_column,
            text="LLM-Powered\nSocial Simulations",
            font=("Helvetica", 9),
            fg="#a0a0a0",
            bg="#1a1a2e",
            justify=tk.CENTER,
        )
        subtitle_label.pack(pady=(0, 20))

        # Separator line
        separator = tk.Frame(left_column, bg="#0d95e8", height=2)
        separator.pack(fill=tk.X, padx=20, pady=10)

        # Authors section
        authors_title = tk.Label(
            left_column,
            text="Created by:",
            font=("Helvetica", 9, "bold"),
            fg="#0d95e8",
            bg="#1a1a2e",
        )
        authors_title.pack(pady=(10, 5))

        authors_text = (
            "Rossetti, Stella,\n"
            "Cazabet, Abramski, Cau,\n"
            "Citraro, Failla, Improta,\n"
            "Morini, Pansanella"
        )
        authors_label = tk.Label(
            left_column,
            text=authors_text,
            font=("Helvetica", 8),
            fg="#cccccc",
            bg="#1a1a2e",
            justify=tk.CENTER,
        )
        authors_label.pack(pady=(0, 10))

        # Release date
        release_label = tk.Label(
            left_column,
            text="Release 2024",
            font=("Helvetica", 9, "bold"),
            fg="#0d95e8",
            bg="#1a1a2e",
        )
        release_label.pack(pady=(5, 10))

        # Loading indicator at bottom
        self.loading_label = tk.Label(
            left_column,
            text="Initializing...",
            font=("Helvetica", 8),
            fg="#ffffff",
            bg="#1a1a2e",
        )
        self.loading_label.pack(side=tk.BOTTOM, pady=(0, 20))

        # Progress bar
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
            # Fallback if robot image can't be loaded
            placeholder = tk.Label(
                right_column,
                text="🤖",
                font=("Helvetica", 48),
                fg="#0d95e8",
                bg="#1a1a2e",
            )
            placeholder.pack(fill=tk.BOTH, expand=True)

    def update_status(self, message):
        """
        Update the loading status message.

        Args:
            message: Status message to display
        """
        if hasattr(self, "loading_label"):
            self.loading_label.config(text=message)
            self.root.update()

    def show(self, duration=2):
        """
        Show the splash screen for a specified duration.

        Args:
            duration: Time to show splash screen in seconds (minimum)
        """
        # Make splash visible immediately
        self.root.update_idletasks()
        self.root.update()

        def close_after_delay():
            time.sleep(duration)
            self.close()

        # Start timer in background thread
        threading.Thread(target=close_after_delay, daemon=True).start()

        # Start the GUI event loop
        try:
            self.root.mainloop()
        except KeyboardInterrupt:
            self.close()

    def close(self):
        """Close the splash screen."""
        try:
            if self.root:
                self.root.quit()
                self.root.destroy()
        except Exception:
            pass


def show_splash_screen(duration=3, status_callback=None):
    """
    Show the YSocial splash screen.

    Args:
        duration: Minimum time to show splash screen in seconds
        status_callback: Optional callback function that receives the splash screen
                        instance for status updates

    Example:
        >>> def init_app(splash):
        ...     splash.update_status("Loading modules...")
        ...     # ... initialization code ...
        ...     splash.update_status("Starting server...")
        >>> show_splash_screen(duration=3, status_callback=init_app)
    """
    splash = YSocialSplashScreen()

    if status_callback:
        # Run callback in background thread
        def run_callback():
            try:
                status_callback(splash)
            except Exception as e:
                print(f"Warning: Status callback error: {e}")

        threading.Thread(target=run_callback, daemon=True).start()

    splash.show(duration)


if __name__ == "__main__":
    # Test the splash screen
    def test_callback(splash):
        """Test callback that simulates initialization."""
        messages = [
            "Loading modules...",
            "Initializing database...",
            "Starting Flask server...",
            "Ready!",
        ]
        for msg in messages:
            time.sleep(0.8)
            splash.update_status(msg)

    show_splash_screen(duration=4, status_callback=test_callback)
