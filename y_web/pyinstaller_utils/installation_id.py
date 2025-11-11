"""
Installation ID management for YSocial.

Generates and stores a unique installation identifier along with
installation metadata (timestamp, country, OS) on first run.
"""

import json
import os
import platform
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


def estimate_country_code():
    """
    Estimate the country code based on system locale.

    Returns:
        str: Two-letter country code (ISO 3166-1 alpha-2) or "XX" if unknown
    """
    try:
        import locale

        # Try to get locale
        try:
            # Get current locale
            current_locale = locale.getlocale()[0]
            if current_locale and "_" in current_locale:
                # Locale format is typically "language_COUNTRY"
                country = current_locale.split("_")[1].split(".")[0]
                if len(country) == 2:
                    return country.upper()
        except Exception:
            pass

        # Try locale.getlocale() with LC_ALL
        try:
            loc = locale.getlocale(locale.LC_ALL)
            if loc and loc[0] and "_" in loc[0]:
                country = loc[0].split("_")[1].split(".")[0]
                if len(country) == 2:
                    return country.upper()
        except Exception:
            pass

    except Exception:
        pass

    # Unknown country
    return "XX"


def get_os_info():
    """
    Get operating system information.

    Returns:
        str: Operating system name and version
    """
    try:
        system = platform.system()
        release = platform.release()
        return f"{system} {release}"
    except Exception:
        return "Unknown"


def get_or_create_installation_id():
    """
    Get existing installation ID or create a new one.

    Returns:
        dict: Installation information containing:
            - installation_id: Unique UUID for this installation
            - timestamp: ISO format timestamp of first installation
            - country: Estimated two-letter country code
            - os: Operating system information
    """
    config_dir = get_installation_config_dir()
    id_file = config_dir / "installation_id.json"

    # Check if installation ID already exists
    if id_file.exists():
        try:
            with open(id_file, "r") as f:
                installation_info = json.load(f)
                # Validate that it has the required fields
                if all(
                    key in installation_info
                    for key in ["installation_id", "timestamp", "country", "os"]
                ):
                    return installation_info
        except Exception as e:
            print(f"Warning: Could not read installation ID: {e}")

    # Generate new installation ID
    from datetime import timezone

    installation_info = {
        "installation_id": str(uuid.uuid4()),
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "country": estimate_country_code(),
        "os": get_os_info(),
    }

    # Save to file
    try:
        with open(id_file, "w") as f:
            json.dump(installation_info, f, indent=2)
        print(f"✓ Created new installation ID: {installation_info['installation_id']}")
        print(f"  Timestamp: {installation_info['timestamp']}")
        print(f"  Country: {installation_info['country']}")
        print(f"  OS: {installation_info['os']}")
        print(f"  Config saved to: {id_file}")
    except Exception as e:
        print(f"Warning: Could not save installation ID: {e}")

    return installation_info


if __name__ == "__main__":
    # Test the installation ID generation
    info = get_or_create_installation_id()
    print("\nInstallation Information:")
    print(json.dumps(info, indent=2))
