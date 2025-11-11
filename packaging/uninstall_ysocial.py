#!/usr/bin/env python3
"""
YSocial Uninstaller

This script removes YSocial and all its generated data files.
Works on macOS, Linux, and Windows.

WARNING: This will permanently delete:
- YSocial application
- All databases (experiments, users, etc.)
- All log files
- All configuration files
- JupyterLab notebooks and data

This action cannot be undone!
"""

import os
import sys
import shutil
import platform
from pathlib import Path


def get_ysocial_paths():
    """
    Determine paths for YSocial installation and data based on platform.
    
    Returns:
        dict: Dictionary containing paths to remove
    """
    system = platform.system()
    home = Path.home()
    
    paths = {
        'app_path': None,
        'data_dirs': [],
        'config_dirs': []
    }
    
    if system == 'Darwin':  # macOS
        paths['app_path'] = Path('/Applications/YSocial.app')
        # Data is stored in the app's working directory where it runs
        # Typically users run it from Downloads or a specific folder
        # We'll check common locations
        possible_data_locations = [
            home / 'YSocial',
            home / 'Documents' / 'YSocial',
            home / 'Downloads' / 'YSocial',
        ]
        for loc in possible_data_locations:
            if loc.exists():
                paths['data_dirs'].append(loc)
                
    elif system == 'Windows':
        paths['app_path'] = Path(os.environ.get('PROGRAMFILES', 'C:\\Program Files')) / 'YSocial'
        paths['data_dirs'].append(home / 'YSocial')
        paths['config_dirs'].append(home / 'AppData' / 'Local' / 'YSocial')
        
    else:  # Linux
        paths['app_path'] = Path('/opt/YSocial')
        paths['data_dirs'].append(home / 'YSocial')
        paths['data_dirs'].append(home / '.ysocial')
        paths['config_dirs'].append(home / '.config' / 'ysocial')
    
    return paths


def find_ysocial_data_in_cwd():
    """
    Find YSocial data directories in common locations relative to where
    users might have run the application.
    
    Returns:
        list: List of Path objects containing YSocial data
    """
    data_dirs = []
    
    # Check current working directory
    cwd = Path.cwd()
    if (cwd / 'y_web').exists() or (cwd / 'db').exists():
        data_dirs.append(cwd)
    
    # Check for y_web subdirectory which indicates YSocial data
    for root, dirs, files in os.walk(Path.home(), topdown=True):
        # Limit depth to avoid scanning entire filesystem
        depth = len(Path(root).relative_to(Path.home()).parts)
        if depth > 3:
            dirs.clear()  # Don't recurse deeper
            continue
            
        if 'y_web' in dirs and any(d in dirs for d in ['db', 'logs', 'config_files']):
            data_dirs.append(Path(root))
            dirs.clear()  # Don't recurse into this directory
    
    return data_dirs


def get_directory_size(path):
    """Calculate total size of a directory in bytes."""
    total = 0
    try:
        for entry in os.scandir(path):
            if entry.is_file(follow_symlinks=False):
                total += entry.stat().st_size
            elif entry.is_dir(follow_symlinks=False):
                total += get_directory_size(entry.path)
    except (PermissionError, FileNotFoundError):
        pass
    return total


def format_size(bytes_size):
    """Format bytes as human-readable size."""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if bytes_size < 1024.0:
            return f"{bytes_size:.1f} {unit}"
        bytes_size /= 1024.0
    return f"{bytes_size:.1f} TB"


def confirm_uninstall(paths_to_remove):
    """
    Show user what will be deleted and ask for confirmation.
    
    Args:
        paths_to_remove: List of Path objects to be removed
        
    Returns:
        bool: True if user confirms, False otherwise
    """
    print("\n" + "="*70)
    print("YSocial Uninstaller")
    print("="*70)
    print("\nThe following items will be permanently deleted:\n")
    
    total_size = 0
    found_items = False
    
    for path in paths_to_remove:
        if path.exists():
            found_items = True
            size = get_directory_size(path) if path.is_dir() else path.stat().st_size
            total_size += size
            item_type = "Directory" if path.is_dir() else "File"
            print(f"  [{item_type}] {path}")
            print(f"             Size: {format_size(size)}")
    
    if not found_items:
        print("  No YSocial files found on this system.")
        return False
    
    print(f"\nTotal size to be freed: {format_size(total_size)}")
    print("\n" + "="*70)
    print("WARNING: This action cannot be undone!")
    print("="*70)
    
    response = input("\nDo you want to continue? Type 'yes' to proceed: ").strip().lower()
    return response == 'yes'


def remove_path(path):
    """
    Safely remove a file or directory.
    
    Args:
        path: Path object to remove
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        if path.is_file() or path.is_symlink():
            path.unlink()
            print(f"  ✓ Removed: {path}")
            return True
        elif path.is_dir():
            shutil.rmtree(path)
            print(f"  ✓ Removed: {path}")
            return True
    except PermissionError:
        print(f"  ✗ Permission denied: {path}")
        print(f"    Try running with administrator/sudo privileges")
        return False
    except Exception as e:
        print(f"  ✗ Error removing {path}: {e}")
        return False
    
    return False


def main():
    """Main uninstall function."""
    print("\nScanning for YSocial installation...")
    
    # Get standard paths
    paths_info = get_ysocial_paths()
    paths_to_remove = []
    
    # Add app path if it exists
    if paths_info['app_path'] and paths_info['app_path'].exists():
        paths_to_remove.append(paths_info['app_path'])
    
    # Add data directories
    for data_dir in paths_info['data_dirs']:
        if data_dir.exists():
            paths_to_remove.append(data_dir)
    
    # Add config directories
    for config_dir in paths_info['config_dirs']:
        if config_dir.exists():
            paths_to_remove.append(config_dir)
    
    # Search for additional YSocial data directories
    print("Searching for YSocial data directories...")
    additional_dirs = find_ysocial_data_in_cwd()
    for data_dir in additional_dirs:
        if data_dir not in paths_to_remove and data_dir.exists():
            paths_to_remove.append(data_dir)
    
    # Remove duplicates and sort
    paths_to_remove = sorted(set(paths_to_remove))
    
    if not paths_to_remove:
        print("\n✓ No YSocial installation found on this system.")
        return 0
    
    # Confirm with user
    if not confirm_uninstall(paths_to_remove):
        print("\nUninstallation cancelled.")
        return 1
    
    # Perform uninstallation
    print("\nRemoving YSocial...\n")
    success_count = 0
    fail_count = 0
    
    for path in paths_to_remove:
        if remove_path(path):
            success_count += 1
        else:
            fail_count += 1
    
    # Summary
    print("\n" + "="*70)
    if fail_count == 0:
        print("✓ YSocial has been successfully uninstalled!")
        print(f"  Removed {success_count} item(s)")
    else:
        print("⚠ YSocial uninstallation completed with errors")
        print(f"  Successfully removed: {success_count} item(s)")
        print(f"  Failed to remove: {fail_count} item(s)")
        print("\nSome items may require administrator/sudo privileges.")
    print("="*70 + "\n")
    
    return 0 if fail_count == 0 else 1


if __name__ == '__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\nUninstallation cancelled by user.")
        sys.exit(1)
    except Exception as e:
        print(f"\n\nUnexpected error: {e}")
        sys.exit(1)
