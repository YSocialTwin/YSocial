#!/usr/bin/env python3
"""
YSocial Uninstaller

This script removes YSocial and all its generated data files.
Works on macOS, Linux, and Windows.

WARNING: This will permanently delete:
- YSocial application (.app bundle or PyInstaller executable)
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


def find_installation_id_file():
    """
    Find the installation_id.json file based on platform.
    
    Returns:
        Path or None: Path to installation_id.json if it exists, None otherwise
    """
    system = platform.system()
    home = Path.home()
    
    # Determine config directory based on platform (same logic as installation_id.py)
    if system == "Windows":
        config_dir = Path(os.getenv("APPDATA", str(home))) / "YSocial"
    elif system == "Darwin":  # macOS
        config_dir = home / "Library" / "Application Support" / "YSocial"
    else:  # Linux and others
        config_dir = home / ".config" / "ysocial"
    
    id_file = config_dir / "installation_id.json"
    if id_file.exists():
        return id_file
    return None


def find_pyinstaller_executables():
    """
    Find PyInstaller standalone executables in common locations.
    
    Returns:
        list: List of Path objects pointing to PyInstaller executables
    """
    executables = []
    home = Path.home()
    system = platform.system()
    
    # Common locations where users might have the PyInstaller executable
    search_paths = [
        home / 'Downloads',
        home / 'Desktop',
        home / 'Documents',
        home / 'Applications',
        Path.cwd(),
    ]
    
    # Executable name patterns based on platform
    if system == 'Windows':
        patterns = ['YSocial.exe', 'YSocial', 'ysocial.exe', 'ysocial']
    else:
        patterns = ['YSocial', 'ysocial']
    
    for search_path in search_paths:
        if not search_path.exists():
            continue
            
        # Search in the immediate directory and dist/ subdirectory
        for pattern in patterns:
            # Check direct location
            exe_path = search_path / pattern
            if exe_path.is_file() and os.access(exe_path, os.X_OK):
                # Verify it's likely a PyInstaller executable by checking size (>10MB typically)
                if exe_path.stat().st_size > 10 * 1024 * 1024:
                    if exe_path not in executables:
                        executables.append(exe_path)
            
            # Check in dist/ subdirectory (PyInstaller default output)
            dist_exe_path = search_path / 'dist' / pattern
            if dist_exe_path.is_file() and os.access(dist_exe_path, os.X_OK):
                if dist_exe_path.stat().st_size > 10 * 1024 * 1024:
                    if dist_exe_path not in executables:
                        executables.append(dist_exe_path)
    
    return executables


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
    print("\nThe following items were found:\n")
    
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


def select_items_to_remove(paths_to_remove):
    """
    Allow user to select which items to remove.
    
    Args:
        paths_to_remove: List of Path objects that can be removed
        
    Returns:
        list: List of Path objects selected for removal
    """
    print("\n" + "="*70)
    print("YSocial Uninstaller - Select Items to Remove")
    print("="*70)
    print("\nThe following items were found:\n")
    
    # Create a list of items with their details
    items = []
    for i, path in enumerate(paths_to_remove, 1):
        if path.exists():
            size = get_directory_size(path) if path.is_dir() else path.stat().st_size
            item_type = "Directory" if path.is_dir() else "File"
            items.append({
                'number': i,
                'path': path,
                'size': size,
                'type': item_type
            })
            print(f"  [{i}] [{item_type}] {path}")
            print(f"      Size: {format_size(size)}")
    
    if not items:
        print("  No YSocial files found on this system.")
        return []
    
    total_size = sum(item['size'] for item in items)
    print(f"\nTotal size: {format_size(total_size)}")
    
    print("\n" + "="*70)
    print("Selection Options:")
    print("  - Enter item numbers separated by spaces (e.g., '1 3 5')")
    print("  - Enter 'all' to select all items")
    print("  - Enter 'none' or press Enter to cancel")
    print("="*70)
    
    while True:
        response = input("\nYour selection: ").strip().lower()
        
        if response == '' or response == 'none':
            return []
        
        if response == 'all':
            return [item['path'] for item in items]
        
        # Parse selection
        try:
            numbers = [int(n.strip()) for n in response.split()]
            selected = []
            invalid = []
            
            for num in numbers:
                if 1 <= num <= len(items):
                    selected.append(items[num - 1]['path'])
                else:
                    invalid.append(num)
            
            if invalid:
                print(f"  ⚠ Invalid item numbers: {', '.join(map(str, invalid))}")
                print(f"  Please enter numbers between 1 and {len(items)}")
                continue
            
            if selected:
                # Show selected items and confirm
                print(f"\n  Selected {len(selected)} item(s):")
                selected_size = 0
                for item in items:
                    if item['path'] in selected:
                        print(f"    [{item['number']}] {item['path']}")
                        selected_size += item['size']
                print(f"\n  Total size to be freed: {format_size(selected_size)}")
                
                confirm = input("\n  Confirm selection? (yes/no): ").strip().lower()
                if confirm == 'yes':
                    return selected
                else:
                    print("\n  Selection cancelled. Please select again.")
                    continue
            else:
                print("  No items selected.")
                return []
                
        except ValueError:
            print("  ⚠ Invalid input. Please enter numbers, 'all', or 'none'.")
            continue


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
    
    # Search for installation_id.json file
    print("Searching for installation ID file...")
    install_id_file = find_installation_id_file()
    if install_id_file:
        paths_to_remove.append(install_id_file)
    
    # Search for additional YSocial data directories
    print("Searching for YSocial data directories...")
    additional_dirs = find_ysocial_data_in_cwd()
    for data_dir in additional_dirs:
        if data_dir not in paths_to_remove and data_dir.exists():
            paths_to_remove.append(data_dir)
    
    # Search for PyInstaller executables
    print("Searching for PyInstaller executables...")
    pyinstaller_exes = find_pyinstaller_executables()
    for exe_path in pyinstaller_exes:
        if exe_path not in paths_to_remove and exe_path.exists():
            paths_to_remove.append(exe_path)
    
    # Remove duplicates and sort
    paths_to_remove = sorted(set(paths_to_remove))
    
    if not paths_to_remove:
        print("\n✓ No YSocial installation found on this system.")
        return 0
    
    # Let user select which items to remove
    selected_paths = select_items_to_remove(paths_to_remove)
    
    if not selected_paths:
        print("\nUninstallation cancelled.")
        return 1
    
    # Final confirmation with warning
    print("\n" + "="*70)
    print("WARNING: This action cannot be undone!")
    print("="*70)
    final_confirm = input("\nType 'DELETE' to proceed with removal: ").strip()
    
    if final_confirm != 'DELETE':
        print("\nUninstallation cancelled.")
        return 1
    
    # Perform uninstallation
    print("\nRemoving selected items...\n")
    success_count = 0
    fail_count = 0
    
    for path in selected_paths:
        if remove_path(path):
            success_count += 1
        else:
            fail_count += 1
    
    # Summary
    print("\n" + "="*70)
    if fail_count == 0:
        print("✓ Selected items have been successfully removed!")
        print(f"  Removed {success_count} item(s)")
    else:
        print("⚠ Removal completed with errors")
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
