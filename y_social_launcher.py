#!/usr/bin/env python
"""
YSocial Launcher Entry Point.

This script serves as the entry point for PyInstaller builds.
For frozen executables, it shows a fast splash screen before loading the main app.
For development, it directly launches the main application.
"""

if __name__ == "__main__":
    import sys
    
    # Check if running as PyInstaller bundle
    is_frozen = getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS")
    
    if is_frozen:
        # For frozen builds, show splash immediately before any heavy imports
        # Import only the lightweight modules needed for splash
        import threading
        
        # Import and show the fast splash screen
        from y_web.pyinstaller_utils.fast_splash import FastSplashScreen
        
        # Create and show splash immediately
        splash = FastSplashScreen()
        
        # Now import and launch the main application in a background thread
        def launch_main():
            """Launch the main application."""
            try:
                # Import the main launcher (heavy imports happen here)
                from y_web.pyinstaller_utils.y_social_launcher import main
                
                # Close splash before starting the app
                splash.close()
                
                # Launch the main application
                main()
            except Exception as e:
                # If something goes wrong, still close the splash
                try:
                    splash.close()
                except Exception:
                    pass
                raise e
        
        # Start main app in background thread
        app_thread = threading.Thread(target=launch_main, daemon=True)
        app_thread.start()
        
        # Run the splash screen main loop (blocks until closed)
        try:
            splash.root.mainloop()
        except Exception:
            pass
        
        # Wait for the app thread to complete
        app_thread.join()
    else:
        # For development, launch directly without splash
        from y_web.pyinstaller_utils.y_social_launcher import main
        main()
