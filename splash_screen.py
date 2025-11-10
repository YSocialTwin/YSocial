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

        # Set window size
        window_width = 600
        window_height = 500

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
        """Create the splash screen content."""
        # Top section with logo
        top_frame = tk.Frame(self.main_frame, bg="#1a1a2e")
        top_frame.pack(pady=20)

        # Load and display YSocial logo
        try:
            logo_path = self._get_resource_path("images/YSocial_v.png")
            logo_img = Image.open(logo_path)
            # Resize logo to fit nicely
            logo_img = logo_img.resize((200, 200), Image.Resampling.LANCZOS)
            self.logo_photo = ImageTk.PhotoImage(logo_img)
            logo_label = tk.Label(top_frame, image=self.logo_photo, bg="#1a1a2e")
            logo_label.pack()
        except Exception as e:
            # Fallback if logo can't be loaded
            print(f"Warning: Could not load logo: {e}")
            logo_label = tk.Label(
                top_frame,
                text="YSocial",
                font=("Helvetica", 32, "bold"),
                fg="#0d95e8",
                bg="#1a1a2e",
            )
            logo_label.pack()

        # Middle section with robot image
        middle_frame = tk.Frame(self.main_frame, bg="#1a1a2e")
        middle_frame.pack(pady=10)

        try:
            robot_path = self._get_resource_path(
                "y_web/static/assets/img/robots/header3.jpg"
            )
            robot_img = Image.open(robot_path)
            # Resize robot image
            robot_img = robot_img.resize((120, 80), Image.Resampling.LANCZOS)
            self.robot_photo = ImageTk.PhotoImage(robot_img)
            robot_label = tk.Label(middle_frame, image=self.robot_photo, bg="#1a1a2e")
            robot_label.pack()
        except Exception as e:
            print(f"Warning: Could not load robot image: {e}")

        # Title
        title_label = tk.Label(
            self.main_frame,
            text="Social Media Digital Twin",
            font=("Helvetica", 14, "bold"),
            fg="#ffffff",
            bg="#1a1a2e",
        )
        title_label.pack(pady=(10, 5))

        # Subtitle
        subtitle_label = tk.Label(
            self.main_frame,
            text="LLM-Powered Social Simulations",
            font=("Helvetica", 10),
            fg="#a0a0a0",
            bg="#1a1a2e",
        )
        subtitle_label.pack(pady=(0, 15))

        # Authors section
        authors_frame = tk.Frame(self.main_frame, bg="#1a1a2e")
        authors_frame.pack(pady=5)

        authors_title = tk.Label(
            authors_frame,
            text="Created by:",
            font=("Helvetica", 9, "bold"),
            fg="#0d95e8",
            bg="#1a1a2e",
        )
        authors_title.pack()

        authors_text = (
            "Rossetti, Stella, Cazabet, Abramski, Cau,\n"
            "Citraro, Failla, Improta, Morini, Pansanella"
        )
        authors_label = tk.Label(
            authors_frame,
            text=authors_text,
            font=("Helvetica", 8),
            fg="#cccccc",
            bg="#1a1a2e",
            justify=tk.CENTER,
        )
        authors_label.pack()

        # Release date
        release_frame = tk.Frame(self.main_frame, bg="#1a1a2e")
        release_frame.pack(pady=5)

        release_label = tk.Label(
            release_frame,
            text="Release 2024",
            font=("Helvetica", 9, "bold"),
            fg="#0d95e8",
            bg="#1a1a2e",
        )
        release_label.pack()

        # Loading indicator
        loading_frame = tk.Frame(self.main_frame, bg="#1a1a2e")
        loading_frame.pack(pady=15)

        self.loading_label = tk.Label(
            loading_frame,
            text="Initializing YSocial...",
            font=("Helvetica", 9),
            fg="#ffffff",
            bg="#1a1a2e",
        )
        self.loading_label.pack()

        # Progress bar with custom style
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
            loading_frame,
            length=400,
            mode="indeterminate",
            style="Custom.Horizontal.TProgressbar",
        )
        self.progress.pack(pady=10)
        self.progress.start(10)

        # Version/License info at bottom
        bottom_label = tk.Label(
            self.main_frame,
            text="GPL v3 License",
            font=("Helvetica", 8),
            fg="#666666",
            bg="#1a1a2e",
        )
        bottom_label.pack(side=tk.BOTTOM, pady=10)

    def update_status(self, message):
        """
        Update the loading status message.

        Args:
            message: Status message to display
        """
        if hasattr(self, "loading_label"):
            self.loading_label.config(text=message)
            self.root.update()

    def show(self, duration=3):
        """
        Show the splash screen for a specified duration.

        Args:
            duration: Time to show splash screen in seconds (minimum)
        """
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
