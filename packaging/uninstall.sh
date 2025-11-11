#!/bin/bash
# YSocial Uninstaller Wrapper for macOS/Linux
# This script runs the Python uninstaller with appropriate permissions

set -e

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
UNINSTALLER="$SCRIPT_DIR/.uninstall_ysocial.py"

echo "YSocial Uninstaller"
echo "==================="
echo ""

# Check if Python 3 is available
if command -v python3 &> /dev/null; then
    PYTHON_CMD="python3"
elif command -v python &> /dev/null; then
    PYTHON_CMD="python"
else
    echo "Error: Python 3 is required but not found."
    echo "Please install Python 3 and try again."
    exit 1
fi

# Check if uninstaller script exists
if [ ! -f "$UNINSTALLER" ]; then
    echo "Error: Uninstaller script not found at $UNINSTALLER"
    exit 1
fi

# Run the uninstaller
"$PYTHON_CMD" "$UNINSTALLER"
exit_code=$?

# If permission error, suggest sudo
if [ $exit_code -ne 0 ]; then
    echo ""
    echo "If you encountered permission errors, try running with sudo:"
    echo "  sudo $0"
fi

exit $exit_code
