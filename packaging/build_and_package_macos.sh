#!/bin/bash
# Automated Build and Package Script for YSocial macOS
# This script automates the complete build, sign, and DMG creation process
#
# Usage:
#   ./packaging/build_and_package_macos.sh [--dev-id "Developer ID Application: Your Name"] [--no-timestamp]
#
# If --dev-id is not provided, uses ad-hoc signing (--sign -)
# Use --no-timestamp for faster signing (skips Apple timestamp server)
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
USE_TIMESTAMP="--timestamp"  # Default to using timestamp
while [[ $# -gt 0 ]]; do
    case $1 in
        --dev-id)
            CODESIGN_IDENTITY="$2"
            shift 2
            ;;
        --no-timestamp)
            USE_TIMESTAMP=""
            shift
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: $0 [--dev-id \"Developer ID Application: Your Name\"] [--no-timestamp]"
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

if [ ! -f "$SCRIPT_DIR/entitlements.plist" ]; then
    echo "❌ Error: entitlements.plist not found in packaging directory"
    exit 1
fi

cd "$PROJECT_ROOT"

# Step 1: Build the executable with PyInstaller
echo "📦 Step 1/3: Building executable with PyInstaller..."
echo "   Command: pyinstaller y_social.spec --clean --noconfirm"
pyinstaller y_social.spec --clean --noconfirm

# With multi-file packaging, PyInstaller creates a directory dist/YSocial
# containing the executable and all dependencies
if [ ! -d "dist/YSocial" ]; then
    echo "❌ Error: Build failed - dist/YSocial directory not found"
    exit 1
fi

if [ ! -f "dist/YSocial/YSocial" ]; then
    echo "❌ Error: Build failed - dist/YSocial/YSocial executable not found"
    exit 1
fi

echo "✅ Build complete: dist/YSocial/ (multi-file bundle)"
echo ""

# Step 2: Sign the executable and all libraries
echo "🔐 Step 2/3: Signing executable bundle with entitlements..."
if [ "$CODESIGN_IDENTITY" = "-" ]; then
    echo "   Using ad-hoc signing (--sign -)"
else
    echo "   Using Developer ID: $CODESIGN_IDENTITY"
fi

if [ -z "$USE_TIMESTAMP" ]; then
    echo "   Skipping timestamp server (--no-timestamp flag)"
fi

# Sign all .dylib and .so files first (dependencies)
echo "   Signing dependencies..."
find dist/YSocial -type f \( -name "*.dylib" -o -name "*.so" \) -exec codesign --force --sign "$CODESIGN_IDENTITY" $USE_TIMESTAMP --options runtime {} \; 2>/dev/null || true

# Sign the main executable with entitlements
echo "   Signing main executable with entitlements..."
codesign --force --sign "$CODESIGN_IDENTITY" \
  --entitlements "$SCRIPT_DIR/entitlements.plist" \
  $USE_TIMESTAMP \
  --options runtime \
  dist/YSocial/YSocial

# Verify the signature
echo "   Verifying signature..."
codesign --verify --verbose dist/YSocial/YSocial

# Verify entitlements were applied
echo "   Checking entitlements..."
if codesign -d --entitlements - dist/YSocial/YSocial 2>&1 | grep -q "com.apple.security.cs.disable-library-validation"; then
    echo "   ✅ Entitlements verified"
else
    echo "   ⚠️  WARNING: Entitlements may not have been applied correctly!"
    echo "   The app might not work on other machines."
    echo "   Checking what was applied:"
    codesign -d --entitlements - dist/YSocial/YSocial 2>&1 | head -20
fi

echo "✅ Executable bundle signed successfully"
echo ""

# Step 3: Create the DMG with signed .app bundle
echo "💿 Step 3/3: Creating DMG installer with signed .app bundle..."
./packaging/create_dmg.sh --codesign-identity "$CODESIGN_IDENTITY" --entitlements "packaging/entitlements.plist"

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
echo "   Executable Bundle: dist/YSocial/"
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
