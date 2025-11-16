#!/bin/bash
# create_dmg.sh – Corrected DMG builder for YSocial with custom background and icons

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

APP_NAME="YSocial"
DIST_DIR="$PROJECT_ROOT/dist"
SRC_DIR="$DIST_DIR/YSocial_dist"
DMG_STAGING="$PROJECT_ROOT/dmg_staging"
BACKGROUND_IMAGE="y_web/static/assets/img/installer/background.png"
ICON_FILE="images/YSocial_ico.png"

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

# Create .icns icon from PNG
if [ -f "$PROJECT_ROOT/$ICON_FILE" ]; then
    echo "🎨 Converting icon to .icns format..."
    if command -v sips &> /dev/null && command -v iconutil &> /dev/null; then
        ICONSET_DIR="$DMG_STAGING/YSocial.iconset"
        mkdir -p "$ICONSET_DIR"
        
        # Generate different icon sizes
        sips -z 16 16     "$PROJECT_ROOT/$ICON_FILE" --out "$ICONSET_DIR/icon_16x16.png" &> /dev/null
        sips -z 32 32     "$PROJECT_ROOT/$ICON_FILE" --out "$ICONSET_DIR/icon_16x16@2x.png" &> /dev/null
        sips -z 32 32     "$PROJECT_ROOT/$ICON_FILE" --out "$ICONSET_DIR/icon_32x32.png" &> /dev/null
        sips -z 64 64     "$PROJECT_ROOT/$ICON_FILE" --out "$ICONSET_DIR/icon_32x32@2x.png" &> /dev/null
        sips -z 128 128   "$PROJECT_ROOT/$ICON_FILE" --out "$ICONSET_DIR/icon_128x128.png" &> /dev/null
        sips -z 256 256   "$PROJECT_ROOT/$ICON_FILE" --out "$ICONSET_DIR/icon_128x128@2x.png" &> /dev/null
        sips -z 256 256   "$PROJECT_ROOT/$ICON_FILE" --out "$ICONSET_DIR/icon_256x256.png" &> /dev/null
        sips -z 512 512   "$PROJECT_ROOT/$ICON_FILE" --out "$ICONSET_DIR/icon_256x256@2x.png" &> /dev/null
        sips -z 512 512   "$PROJECT_ROOT/$ICON_FILE" --out "$ICONSET_DIR/icon_512x512.png" &> /dev/null
        sips -z 1024 1024 "$PROJECT_ROOT/$ICON_FILE" --out "$ICONSET_DIR/icon_512x512@2x.png" &> /dev/null
        
        # Convert to icns
        iconutil -c icns "$ICONSET_DIR" -o "$APP_BUNDLE/Contents/Resources/YSocial.icns"
        rm -rf "$ICONSET_DIR"
        echo "   ✅ Icon converted successfully"
    else
        echo "   ⚠️  sips/iconutil not available, skipping icon conversion"
    fi
else
    echo "⚠️  Icon file not found, skipping icon conversion"
fi

# Add Info.plist CFBundleIconFile key
echo "➡️ Updating Info.plist with icon..."
cat > "$APP_BUNDLE/Contents/Info.plist" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleExecutable</key>
    <string>${APP_NAME}</string>
    <key>CFBundleIconFile</key>
    <string>YSocial</string>
    <key>CFBundleIdentifier</key>
    <string>com.ysocialtwin.ysocial</string>
    <key>CFBundleName</key>
    <string>${APP_NAME}</string>
    <key>CFBundleDisplayName</key>
    <string>YSocial</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleVersion</key>
    <string>2.0.0</string>
    <key>CFBundleShortVersionString</key>
    <string>2.0.0</string>
</dict>
</plist>
EOF

# Setup DMG background and Applications symlink
echo "🖼️  Setting up DMG customization..."
DMG_BG_DIR="$DMG_STAGING/.background"
mkdir -p "$DMG_BG_DIR"

if [ -f "$PROJECT_ROOT/$BACKGROUND_IMAGE" ]; then
    cp "$PROJECT_ROOT/$BACKGROUND_IMAGE" "$DMG_BG_DIR/background.png"
    echo "   ✅ Background image added"
else
    echo "   ⚠️  Background image not found"
fi

# Create Applications symlink
ln -s /Applications "$DMG_STAGING/Applications"
echo "   ✅ Applications symlink created"


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

APP_SIZE_BYTES=$(du -sk "$DMG_STAGING" | awk '{print $1}')
# Add 15% overhead + 100MB for filesystem metadata and safety margin
# Multi-file PyInstaller bundles need more overhead due to many small files
DMG_SIZE_MB=$(( APP_SIZE_BYTES / 1024 * 115 / 100 + 100 ))

echo "   Staging size: $((APP_SIZE_BYTES/1024)) MB"
echo "   DMG size: ${DMG_SIZE_MB} MB"

echo "➡️ Creating temporary DMG..."

hdiutil create -srcfolder "$DMG_STAGING" -volname "YSocial" -fs HFS+ \
    -fsargs "-c c=64,a=16,e=16" -format UDRW -size ${DMG_SIZE_MB}m "$TEMP_DMG"

# Mount the temporary DMG
echo "📂 Mounting temporary DMG..."
MOUNT_DIR="/Volumes/YSocial"

# Unmount if already mounted
if [ -d "$MOUNT_DIR" ]; then
    echo "   Unmounting existing volume..."
    hdiutil detach "$MOUNT_DIR" 2>/dev/null || true
    sleep 1
fi

hdiutil attach -readwrite -noverify -noautoopen "$TEMP_DMG" | egrep '^/dev/' | sed 1q | awk '{print $1}' > /tmp/dmg_device.txt
DMG_DEVICE=$(cat /tmp/dmg_device.txt)

# Wait for mount to complete
sleep 3

# Set custom DMG appearance using AppleScript
echo "🎨 Customizing DMG appearance..."
cat > /tmp/dmg_customization.applescript << 'ASCRIPT'
tell application "Finder"
    tell disk "YSocial"
        open
        set current view of container window to icon view
        set toolbar visible of container window to false
        set statusbar visible of container window to false
        set the bounds of container window to {400, 100, 1070, 520}
        set viewOptions to the icon view options of container window
        set arrangement of viewOptions to not arranged
        set icon size of viewOptions to 72
        set background picture of viewOptions to file ".background:background.png"

        -- Position icons (centered to align with arrow in background)
        set position of item "YSocial.app" of container window to {150, 180}
        set position of item "Applications" of container window to {450, 180}

        close
        open
        update without registering applications
        delay 5
    end tell
end tell
ASCRIPT

# Only apply AppleScript customization if background exists
if [ -f "$MOUNT_DIR/.background/background.png" ]; then
    osascript /tmp/dmg_customization.applescript || echo "⚠️  Warning: Could not apply visual customization"
    sleep 2
else
    echo "⚠️  No background found, skipping visual customization"
fi

# Set custom icon for DMG volume if available
MOUNTED_APP_BUNDLE="$MOUNT_DIR/YSocial.app"
if [ -f "$MOUNTED_APP_BUNDLE/Contents/Resources/YSocial.icns" ]; then
    echo "🎨 Setting DMG volume icon..."
    if cp "$MOUNTED_APP_BUNDLE/Contents/Resources/YSocial.icns" "$MOUNT_DIR/.VolumeIcon.icns" 2>/dev/null; then
        SetFile -c icnC "$MOUNT_DIR/.VolumeIcon.icns" 2>/dev/null || true
        SetFile -a C "$MOUNT_DIR" 2>/dev/null || true
        echo "   ✅ Volume icon set successfully"
    else
        echo "   ⚠️  Warning: Could not set volume icon"
    fi
else
    echo "   ℹ️  No custom icon found, skipping volume icon"
fi

# Hide background folder
SetFile -a V "$MOUNT_DIR/.background" 2>/dev/null || true

# Unmount
echo "📤 Unmounting temporary DMG..."
hdiutil detach "$DMG_DEVICE"
sleep 2

# Convert to compressed final DMG
echo "🗜️  Compressing final DMG..."
hdiutil convert "$TEMP_DMG" -format UDZO -imagekey zlib-level=9 -o "$DMG_PATH"

# Clean up
echo "🧹 Cleaning up..."
rm -f "$TEMP_DMG"
rm -f /tmp/dmg_customization.applescript
rm -f /tmp/dmg_device.txt

echo "========================================="
echo "🎉 DMG Created:"
echo "   $DMG_PATH"
echo "========================================="
