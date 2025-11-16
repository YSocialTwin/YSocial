#!/bin/bash
# create_dmg.sh – Corrected DMG builder for YSocial

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

APP_NAME="YSocial"
DIST_DIR="$PROJECT_ROOT/dist"
SRC_DIR="$DIST_DIR/YSocial_dist"
DMG_STAGING="$PROJECT_ROOT/dmg_staging"

CODESIGN_IDENTITY=""
ENTITLEMENTS=""

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --codesign-identity)
            CODESIGN_IDENTITY="$2"
            shift 2
            ;;
        --entitlements)
            ENTITLEMENTS="$2"
            shift 2
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

if [ -z "$CODESIGN_IDENTITY" ]; then
    echo "❌ Error: Missing --codesign-identity"
    exit 1
fi

if [ -z "$ENTITLEMENTS" ]; then
    echo "❌ Error: Missing --entitlements path"
    exit 1
fi

echo "========================================="
echo "📦 Creating YSocial.app bundle"
echo "========================================="

rm -rf "$DMG_STAGING"
mkdir -p "$DMG_STAGING"

APP_BUNDLE="$DMG_STAGING/$APP_NAME.app"

mkdir -p "$APP_BUNDLE/Contents/MacOS"
mkdir -p "$APP_BUNDLE/Contents/Resources"
mkdir -p "$APP_BUNDLE/Contents/Resources/dist-info"

echo "➡️ Copying main executable..."
cp "$SRC_DIR/$APP_NAME" "$APP_BUNDLE/Contents/MacOS/"

echo "➡️ Copying binary libs (.so / .dylib)..."
find "$SRC_DIR" -type f \( -name "*.dylib" -o -name "*.so" \) \
    -exec cp {} "$APP_BUNDLE/Contents/MacOS/" \;

echo "➡️ Copying Python runtime (_internal)..."
cp -R "$SRC_DIR/_internal" "$APP_BUNDLE/Contents/Resources/"

echo "➡️ Moving .dist-info metadata..."
find "$SRC_DIR" -maxdepth 2 -type d -name "*.dist-info" \
    -exec mv {} "$APP_BUNDLE/Contents/Resources/dist-info/" \;

# Optional: copy assets/templates/static
if [ -d "$SRC_DIR/static" ]; then
    echo "➡️ Copying static assets..."
    cp -R "$SRC_DIR/static" "$APP_BUNDLE/Contents/Resources/"
fi

if [ -d "$SRC_DIR/templates" ]; then
    echo "➡️ Copying templates..."
    cp -R "$SRC_DIR/templates" "$APP_BUNDLE/Contents/Resources/"
fi


echo "========================================="
echo "🔐 Signing .app bundle"
echo "========================================="

codesign --force --sign "$CODESIGN_IDENTITY" \
  --entitlements "$ENTITLEMENTS" \
  --timestamp \
  --options runtime \
  --deep \
  "$APP_BUNDLE"

echo "✔️ App signed"


echo "========================================="
echo "💿 Building DMG"
echo "========================================="

DMG_PATH="$DIST_DIR/YSocial-2.0.0.dmg"
TEMP_DMG="$DIST_DIR/YSocial-2.0.0_temp.dmg"

echo "➡️ Calculating required DMG size..."

APP_SIZE_BYTES=$(du -sk "$APP_BUNDLE" | awk '{print $1}')
# Add 35% overhead
DMG_SIZE_MB=$(( APP_SIZE_BYTES / 1024 + 50 ))

echo "   App size: $((APP_SIZE_BYTES/1024)) MB"
echo "   DMG size: ${DMG_SIZE_MB} MB"

echo "➡️ Creating temporary DMG..."

hdiutil create -volname "YSocial" \
  -srcfolder "$DMG_STAGING" \
  -ov \
  -format UDZO \
  -size ${DMG_SIZE_MB}m \
  "$TEMP_DMG"

echo "➡️ Converting to final DMG..."
mv "$TEMP_DMG" "$DMG_PATH"

echo "========================================="
echo "🎉 DMG Created:"
echo "   $DMG_PATH"
echo "========================================="
