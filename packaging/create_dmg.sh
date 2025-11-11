#!/bin/bash
# Script to create a macOS .dmg installer for YSocial
# This script packages the PyInstaller-built YSocial executable into a disk image
# with a custom background and drag-to-Applications functionality

set -e  # Exit on error

# Configuration
APP_NAME="YSocial"
VERSION="${VERSION:-2.0.0}"
DMG_NAME="${APP_NAME}-${VERSION}"
SOURCE_APP="dist/${APP_NAME}"
BACKGROUND_IMAGE="y_web/static/assets/img/installer/background.png"
ICON_FILE="images/YSocial_ico.png"

# Directories
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
STAGING_DIR="${PROJECT_ROOT}/dmg_staging"
DMG_DIR="${STAGING_DIR}/.background"
FINAL_DMG="${PROJECT_ROOT}/dist/${DMG_NAME}.dmg"
TEMP_DMG="${PROJECT_ROOT}/dist/${DMG_NAME}_temp.dmg"

# Check if we're on macOS
if [[ "$OSTYPE" != "darwin"* ]]; then
    echo "❌ Error: This script must be run on macOS"
    exit 1
fi

# Check if source app exists
if [ ! -f "$PROJECT_ROOT/$SOURCE_APP" ]; then
    echo "❌ Error: YSocial executable not found at $PROJECT_ROOT/$SOURCE_APP"
    echo "Please build the executable first using: pyinstaller y_social.spec"
    exit 1
fi

echo "🚀 Creating YSocial DMG installer..."
echo "   Version: $VERSION"
echo "   Source: $SOURCE_APP"

# Clean up previous builds
echo "🧹 Cleaning up previous builds..."
rm -rf "$STAGING_DIR"
rm -f "$TEMP_DMG"
rm -f "$FINAL_DMG"

# Create staging directory structure
echo "📁 Creating staging directory..."
mkdir -p "$STAGING_DIR"
mkdir -p "$DMG_DIR"
mkdir -p "$(dirname "$FINAL_DMG")"

# Create .app bundle
echo "📦 Creating YSocial.app bundle..."
APP_BUNDLE="$STAGING_DIR/${APP_NAME}.app"
mkdir -p "$APP_BUNDLE/Contents/MacOS"
mkdir -p "$APP_BUNDLE/Contents/Resources"

# Copy executable to bundle
cp "$PROJECT_ROOT/$SOURCE_APP" "$APP_BUNDLE/Contents/MacOS/${APP_NAME}"
chmod +x "$APP_BUNDLE/Contents/MacOS/${APP_NAME}"

# Create Info.plist
cat > "$APP_BUNDLE/Contents/Info.plist" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleExecutable</key>
    <string>${APP_NAME}</string>
    <key>CFBundleIdentifier</key>
    <string>com.ysocialtwin.ysocial</string>
    <key>CFBundleName</key>
    <string>${APP_NAME}</string>
    <key>CFBundleDisplayName</key>
    <string>YSocial</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleVersion</key>
    <string>${VERSION}</string>
    <key>CFBundleShortVersionString</key>
    <string>${VERSION}</string>
    <key>CFBundleIconFile</key>
    <string>YSocial.icns</string>
    <key>NSHighResolutionCapable</key>
    <true/>
    <key>LSMinimumSystemVersion</key>
    <string>10.13.0</string>
</dict>
</plist>
EOF

# Convert icon to .icns if possible
if [ -f "$PROJECT_ROOT/$ICON_FILE" ]; then
    echo "🎨 Converting icon to .icns format..."
    if command -v sips &> /dev/null && command -v iconutil &> /dev/null; then
        # Create iconset directory
        ICONSET_DIR="$STAGING_DIR/YSocial.iconset"
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
    else
        echo "⚠️  Warning: sips/iconutil not available, skipping icon conversion"
    fi
fi

# Copy background image
if [ -f "$PROJECT_ROOT/$BACKGROUND_IMAGE" ]; then
    echo "🖼️  Adding custom background..."
    cp "$PROJECT_ROOT/$BACKGROUND_IMAGE" "$DMG_DIR/background.png"
else
    echo "⚠️  Warning: Background image not found, DMG will have no custom background"
fi

# Create symbolic link to Applications folder
echo "🔗 Creating Applications symlink..."
ln -s /Applications "$STAGING_DIR/Applications"

# Calculate DMG size (in MB, with 20% padding)
echo "📏 Calculating DMG size..."
APP_SIZE=$(du -sm "$APP_BUNDLE" | cut -f1)
DMG_SIZE=$((APP_SIZE + 100))  # Add 100MB for background and padding

# Create temporary DMG
echo "💿 Creating temporary DMG..."
hdiutil create -srcfolder "$STAGING_DIR" -volname "$APP_NAME" -fs HFS+ \
    -fsargs "-c c=64,a=16,e=16" -format UDRW -size ${DMG_SIZE}m "$TEMP_DMG"

# Mount the temporary DMG
echo "📂 Mounting temporary DMG..."
MOUNT_DIR="/Volumes/$APP_NAME"
hdiutil attach -readwrite -noverify -noautoopen "$TEMP_DMG" | egrep '^/dev/' | sed 1q | awk '{print $1}' > /tmp/dmg_device.txt
DMG_DEVICE=$(cat /tmp/dmg_device.txt)

# Wait for mount
sleep 2

# Set custom DMG appearance using AppleScript
echo "🎨 Customizing DMG appearance..."
cat > /tmp/dmg_customization.applescript << 'ASCRIPT'
tell application "Finder"
    tell disk "YSocial"
        open
        set current view of container window to icon view
        set toolbar visible of container window to false
        set statusbar visible of container window to false
        set the bounds of container window to {400, 100, 1000, 550}
        set viewOptions to the icon view options of container window
        set arrangement of viewOptions to not arranged
        set icon size of viewOptions to 128
        set background picture of viewOptions to file ".background:background.png"
        
        -- Position icons
        set position of item "YSocial.app" of container window to {150, 200}
        set position of item "Applications" of container window to {450, 200}
        
        close
        open
        update without registering applications
        delay 2
    end tell
end tell
ASCRIPT

# Only apply AppleScript customization if background exists
if [ -f "$MOUNT_DIR/.background/background.png" ]; then
    osascript /tmp/dmg_customization.applescript || echo "⚠️  Warning: Could not apply visual customization"
    sleep 2
fi

# Set custom icon for DMG volume if available
if [ -f "$APP_BUNDLE/Contents/Resources/YSocial.icns" ]; then
    echo "🎨 Setting DMG volume icon..."
    cp "$APP_BUNDLE/Contents/Resources/YSocial.icns" "$MOUNT_DIR/.VolumeIcon.icns"
    SetFile -c icnC "$MOUNT_DIR/.VolumeIcon.icns" 2>/dev/null || true
    SetFile -a C "$MOUNT_DIR" 2>/dev/null || true
fi

# Hide background folder
SetFile -a V "$MOUNT_DIR/.background" 2>/dev/null || true

# Unmount
echo "📤 Unmounting temporary DMG..."
hdiutil detach "$DMG_DEVICE"
sleep 2

# Convert to compressed final DMG
echo "🗜️  Compressing final DMG..."
hdiutil convert "$TEMP_DMG" -format UDZO -imagekey zlib-level=9 -o "$FINAL_DMG"

# Clean up
echo "🧹 Cleaning up..."
rm -f "$TEMP_DMG"
rm -rf "$STAGING_DIR"
rm -f /tmp/dmg_customization.applescript
rm -f /tmp/dmg_device.txt

echo ""
echo "✅ DMG created successfully!"
echo "   Location: $FINAL_DMG"
echo "   Size: $(du -h "$FINAL_DMG" | cut -f1)"
echo ""
echo "🚀 You can now distribute this DMG file to users!"
