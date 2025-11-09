"""
PyInstaller runtime hook for YSocial.

This hook configures NLTK data paths at runtime to work with
the bundled executable.
"""

import os
import sys

# Configure NLTK data path for bundled app
if getattr(sys, 'frozen', False):
    # Running as bundled executable
    bundle_dir = sys._MEIPASS
    nltk_data_path = os.path.join(bundle_dir, 'nltk_data')
    
    # Set NLTK data path
    import nltk
    nltk.data.path.insert(0, nltk_data_path)
