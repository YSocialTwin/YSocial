"""
Installation ID management for YSocial.

Generates and stores a unique installation identifier along with
installation metadata (timestamp, country, OS, version) on first run.
"""

import json
import os
import platform
import sys
import uuid
from datetime import datetime
from pathlib import Path


def get_installation_config_dir():
    """
    Get the directory for storing installation configuration.

    Returns:
        Path: Directory path for installation config
    """
    # Use platform-specific config directory
    if platform.system() == "Windows":
        config_dir = Path(os.getenv("APPDATA", "~")) / "YSocial"
    elif platform.system() == "Darwin":  # macOS
        config_dir = Path.home() / "Library" / "Application Support" / "YSocial"
    else:  # Linux and others
        config_dir = Path.home() / ".config" / "ysocial"

    # Create directory if it doesn't exist
    config_dir = config_dir.expanduser()
    config_dir.mkdir(parents=True, exist_ok=True)

    return config_dir


def get_language():
    """
    Get the language from system locale.

    Returns:
        str: Two-letter language code (ISO 639-1) or "en" if unknown
    """
    try:
        import locale
        import os

        # Try environment variables first (most reliable for system locale)
        for env_var in ['LANG', 'LANGUAGE', 'LC_ALL', 'LC_MESSAGES']:
            env_locale = os.environ.get(env_var)
            if env_locale:
                # Handle format like "en_US.UTF-8" or "en_US"
                if "_" in env_locale:
                    language = env_locale.split("_")[0]
                    if language and len(language) >= 2:
                        return language[:2].lower()
                # Handle format like "C.UTF-8" or "C" (default to en)
                elif env_locale.startswith("C"):
                    continue

        # Try locale.getdefaultlocale()
        try:
            default_locale = locale.getdefaultlocale()
            if default_locale and default_locale[0]:
                if "_" in default_locale[0]:
                    language = default_locale[0].split("_")[0]
                    if language and len(language) >= 2:
                        return language[:2].lower()
        except Exception:
            pass

        # Fallback to getlocale
        try:
            current_locale = locale.getlocale()[0]
            if current_locale and current_locale != 'C':
                if "_" in current_locale:
                    language = current_locale.split("_")[0]
                    if language and len(language) >= 2:
                        return language[:2].lower()
        except Exception:
            pass

    except Exception:
        pass

    # Default to English
    return "en"


def estimate_country_code():
    """
    Estimate the country code based on system locale.

    Returns:
        str: Two-letter country code (ISO 3166-1 alpha-2) or "XX" if unknown
    """
    try:
        import locale
        import os

        # Try environment variables first (most reliable for system locale)
        for env_var in ['LANG', 'LANGUAGE', 'LC_ALL', 'LC_MESSAGES']:
            env_locale = os.environ.get(env_var)
            if env_locale:
                # Handle format like "en_US.UTF-8" or "en_US"
                if "_" in env_locale:
                    parts = env_locale.split("_")[1].split(".")[0]
                    if parts and len(parts) == 2:
                        return parts.upper()
                # Handle format like "C.UTF-8" or "C" (skip)
                elif env_locale.startswith("C"):
                    continue

        # Try locale.getdefaultlocale()
        try:
            default_locale = locale.getdefaultlocale()
            if default_locale and default_locale[0]:
                if "_" in default_locale[0]:
                    country = default_locale[0].split("_")[1].split(".")[0]
                    if country and len(country) == 2:
                        return country.upper()
        except Exception:
            pass

        # Fallback to getlocale
        try:
            current_locale = locale.getlocale()[0]
            if current_locale and current_locale != 'C':
                if "_" in current_locale:
                    country = current_locale.split("_")[1].split(".")[0]
                    if country and len(country) == 2:
                        return country.upper()
        except Exception:
            pass

    except Exception:
        pass

    # Unknown country
    return "XX"


def get_os_type():
    """
    Get operating system type in simple format.

    Returns:
        str: Operating system type: "windows", "macos", "linux", or "other"
    """
    try:
        system = platform.system().lower()
        
        if system == "windows":
            return "windows"
        elif system == "darwin":
            return "macos"
        elif system == "linux":
            return "linux"
        else:
            return "other"
    except Exception:
        return "other"


def get_os_version():
    """
    Get operating system version with full details.

    Returns:
        str: Operating system version details
    """
    try:
        release = platform.release()
        version = platform.version()
        
        # Construct full OS version info
        if version and version != release:
            return f"{release} ({version})"
        else:
            return release
    except Exception:
        return "Unknown"


def get_installation_type():
    """
    Determine the type of YSocial installation.

    Returns:
        str: "app" for PyInstaller bundle, "source" for running from code
    """
    # Check if running from PyInstaller bundle
    if getattr(sys, "frozen", False):
        return "app"
    else:
        return "source"


def get_python_version():
    """
    Get the Python version.

    Returns:
        str: Python version (e.g., "3.9.7")
    """
    try:
        return platform.python_version()
    except Exception:
        return f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"


def get_version():
    """
    Get YSocial version from VERSION file.

    Returns:
        str: Version string (e.g., "2.0.0") or "Unknown" if not available
    """
    try:
        # Try to get resource path (works for both dev and PyInstaller)
        try:
            # PyInstaller creates a temp folder and stores path in _MEIPASS
            base_path = sys._MEIPASS
        except AttributeError:
            base_path = os.path.abspath(".")

        version_path = os.path.join(base_path, "VERSION")
        with open(version_path, "r") as f:
            return f.read().strip()
    except Exception:
        # Fallback: try relative to this file's location
        try:
            current_dir = Path(__file__).parent.parent.parent
            version_path = current_dir / "VERSION"
            with open(version_path, "r") as f:
                return f.read().strip()
        except Exception:
            return "Unknown"


def get_or_create_installation_id():
    """
    Get existing installation ID or create a new one.

    If the installation ID exists but the version has changed, updates the
    version and timestamp fields while preserving the installation_id.

    Returns:
        dict: Installation information containing:
            - installation_id: Unique UUID for this installation
            - timestamp: ISO format timestamp of first installation (or last version update)
            - country: Estimated two-letter country code
            - language: Two-letter language code from locale
            - os: Operating system type (windows, macos, linux, other)
            - os_version: Operating system version details
            - installation_type: "app" (PyInstaller) or "source" (code)
            - python_version: Python version string
            - version: YSocial version at time of installation/update
    """
    from y_web.telemetry import Telemetry

    config_dir = get_installation_config_dir()
    id_file = config_dir / "installation_id.json"

    # Check if installation ID already exists
    if id_file.exists():
        try:
            with open(id_file, "r") as f:
                installation_info = json.load(f)
                # Validate that it has the required fields
                if "installation_id" in installation_info:
                    # Update with new fields if missing (backward compatibility)
                    needs_update = False
                    
                    if "language" not in installation_info:
                        installation_info["language"] = get_language()
                        needs_update = True
                    
                    if "installation_type" not in installation_info:
                        installation_info["installation_type"] = get_installation_type()
                        needs_update = True
                    
                    if "python_version" not in installation_info:
                        installation_info["python_version"] = get_python_version()
                        needs_update = True
                    
                    # Check if we need to split old "os" field into "os" and "os_version"
                    # Old format was like "Linux 6.11.0-1018-azure (#18~24.04.1-Ubuntu SMP...)"
                    # New format: os="linux", os_version="6.11.0-1018-azure (#18~24.04.1-Ubuntu SMP...)"
                    current_os_type = get_os_type()
                    current_os_version = get_os_version()
                    
                    if "os_version" not in installation_info:
                        # Need to migrate from old format
                        installation_info["os"] = current_os_type
                        installation_info["os_version"] = current_os_version
                        needs_update = True
                    else:
                        # Already has new format, just update if needed
                        if installation_info.get("os") != current_os_type:
                            installation_info["os"] = current_os_type
                            needs_update = True
                        if installation_info.get("os_version") != current_os_version:
                            installation_info["os_version"] = current_os_version
                            needs_update = True
                    
                    # Add version if it's missing (for backward compatibility)
                    if "version" not in installation_info:
                        installation_info["version"] = get_version()
                        needs_update = True
                    else:
                        # Check if version has changed
                        current_version = get_version()
                        if installation_info["version"] != current_version:
                            # Update version and timestamp
                            from datetime import timezone

                            installation_info["version"] = current_version
                            installation_info["timestamp"] = (
                                datetime.now(timezone.utc)
                                .isoformat()
                                .replace("+00:00", "Z")
                            )
                            needs_update = True
                            print(
                                f"✓ Updated version from {installation_info.get('version', 'Unknown')} to {current_version}"
                            )
                            print(
                                f"  New timestamp: {installation_info['timestamp']}"
                            )

                            telemetry = Telemetry()
                            telemetry.register_update_app(
                                installation_info, action="update"
                            )
                    
                    # Save updated info if needed
                    if needs_update:
                        try:
                            with open(id_file, "w") as f_out:
                                json.dump(installation_info, f_out, indent=2)
                            print("✓ Updated installation info with new fields")
                        except Exception as e:
                            print(f"Warning: Could not update installation ID: {e}")
                    
                    return installation_info
        except Exception as e:
            print(f"Warning: Could not read installation ID: {e}")

    # Generate new installation ID
    from datetime import timezone

    installation_info = {
        "installation_id": str(uuid.uuid4()),
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "country": estimate_country_code(),
        "language": get_language(),
        "os": get_os_type(),
        "os_version": get_os_version(),
        "installation_type": get_installation_type(),
        "python_version": get_python_version(),
        "version": get_version(),
    }

    # Save to file
    try:
        with open(id_file, "w") as f:
            json.dump(installation_info, f, indent=2)
        print(f"✓ Created new installation ID: {installation_info['installation_id']}")
        print(f"  Timestamp: {installation_info['timestamp']}")
        print(f"  Country: {installation_info['country']}")
        print(f"  Language: {installation_info['language']}")
        print(f"  OS: {installation_info['os']}")
        print(f"  OS Version: {installation_info['os_version']}")
        print(f"  Installation Type: {installation_info['installation_type']}")
        print(f"  Python Version: {installation_info['python_version']}")
        print(f"  Version: {installation_info['version']}")
        print(f"  Config saved to: {id_file}")
    except Exception as e:
        print(f"Warning: Could not save installation ID: {e}")

    telemetry = Telemetry()
    telemetry.register_update_app(installation_info, action="register")

    return installation_info

    telemetry = Telemetry()
    telemetry.register_update_app(installation_info, action="register")

    return installation_info


if __name__ == "__main__":
    # Test the installation ID generation
    info = get_or_create_installation_id()
    print("\nInstallation Information:")
    print(json.dumps(info, indent=2))
