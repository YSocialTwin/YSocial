#!/bin/bash
# Automated Build and Package Script for YSocial macOS
# This script automates the complete build, sign, and DMG creation process
#
# Usage:
#   ./packaging/build_and_package_macos.sh [--dev-id "Developer ID Application: Your Name"]
#
# If --dev-id is not provided, uses ad-hoc signing (--sign -)
#
# Steps performed:
#   1. Build executable with PyInstaller
#   2. Sign the executable with entitlements
#   3. Create DMG installer with signed .app bundle

set -e  # Exit on error

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Parse command line arguments
CODESIGN_IDENTITY="-"  # Default to ad-hoc signing
while [[ $# -gt 0 ]]; do
    case $1 in
        --dev-id)
            CODESIGN_IDENTITY="$2"
            shift 2
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: $0 [--dev-id \"Developer ID Application: Your Name\"]"
            exit 1
            ;;
    esac
done

echo "=================================="
echo "YSocial macOS Build & Package"
echo "=================================="
echo ""

# Check if we're on macOS
if [[ "$OSTYPE" != "darwin"* ]]; then
    echo "❌ Error: This script must be run on macOS"
    exit 1
fi

# Check if required files exist
if [ ! -f "$PROJECT_ROOT/y_social.spec" ]; then
    echo "❌ Error: y_social.spec not found"
    exit 1
fi

if [ ! -f "$PROJECT_ROOT/entitlements.plist" ]; then
    echo "❌ Error: entitlements.plist not found"
    exit 1
fi

cd "$PROJECT_ROOT"

# Step 1: Build the executable with PyInstaller
echo "📦 Step 1/3: Building executable with PyInstaller..."
echo "   Command: pyinstaller y_social.spec --clean --noconfirm"
pyinstaller y_social.spec --clean --noconfirm

if [ ! -f "dist/YSocial" ]; then
    echo "❌ Error: Build failed - dist/YSocial not found"
    exit 1
fi
echo "✅ Build complete: dist/YSocial"
echo ""

# Step 2: Sign the executable
echo "🔐 Step 2/3: Signing executable with entitlements..."
if [ "$CODESIGN_IDENTITY" = "-" ]; then
    echo "   Using ad-hoc signing (--sign -)"
else
    echo "   Using Developer ID: $CODESIGN_IDENTITY"
fi

codesign --force --sign "$CODESIGN_IDENTITY" \
  --entitlements entitlements.plist \
  --timestamp \
  --options runtime \
  dist/YSocial

# Verify the signature
echo "   Verifying signature..."
codesign --verify --verbose dist/YSocial
echo "✅ Executable signed successfully"
echo ""

# Step 3: Create the DMG with signed .app bundle
echo "💿 Step 3/4: Creating DMG installer with signed .app bundle..."
./packaging/create_dmg.sh --codesign-identity "$CODESIGN_IDENTITY" --entitlements entitlements.plist

# Find the created DMG
DMG_FILE=$(find dist -name "YSocial-*.dmg" -type f | head -n 1)
if [ -z "$DMG_FILE" ]; then
    echo "❌ Error: DMG file not found in dist/"
    exit 1
fi
echo "✅ DMG created: $DMG_FILE"

echo ""
echo "=================================="
echo "✅ Build and Package Complete!"
echo "=================================="
echo ""
echo "📦 Output:"
echo "   Executable: dist/YSocial"
echo "   DMG: $DMG_FILE"
echo ""
if [ "$CODESIGN_IDENTITY" = "-" ]; then
    echo "ℹ️  Note: Used ad-hoc signing (--sign -)"
    echo "   For wider distribution, re-run with:"
    echo "   $0 --dev-id \"Developer ID Application: Your Name\""
else
    echo "ℹ️  Signed with: $CODESIGN_IDENTITY"
fi
echo ""
echo "🚀 Ready for distribution!"
