#!/bin/bash
# Build script for YSocial macOS Launcher
# This script compiles the Swift launcher application

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$(dirname "$SCRIPT_DIR")")"

echo "Building YSocial macOS Launcher..."
echo "Script directory: $SCRIPT_DIR"
echo "Project root: $PROJECT_ROOT"

# Compile the Swift launcher
cd "$SCRIPT_DIR"

# Build the launcher executable
# Use -parse-as-library to allow @NSApplicationMain attribute
swiftc -O \
    -parse-as-library \
    -o YSocialLauncher \
    YSocialLauncher.swift

echo "✅ Launcher built successfully: $SCRIPT_DIR/YSocialLauncher"
