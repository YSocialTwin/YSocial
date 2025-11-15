#!/bin/bash
# Script to create a macOS .dmg installer for YSocial
# This script packages the PyInstaller-built YSocial executable into a disk image
# with a custom background and drag-to-Applications functionality
#
# Usage:
#   ./packaging/create_dmg.sh [--codesign-identity "identity"] [--entitlements "path/to/entitlements.plist"]
#
# Examples:
#   ./packaging/create_dmg.sh                                    # No code signing
#   ./packaging/create_dmg.sh --codesign-identity "-"            # Ad-hoc signing
#   ./packaging/create_dmg.sh --codesign-identity "Developer ID Application: Your Name"  # Developer ID

set -e  # Exit on error

# Parse command line arguments
CODESIGN_IDENTITY=""
ENTITLEMENTS_FILE=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --codesign-identity)
            CODESIGN_IDENTITY="$2"
            shift 2
            ;;
        --entitlements)
            ENTITLEMENTS_FILE="$2"
            shift 2
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: $0 [--codesign-identity \"identity\"] [--entitlements \"path/to/entitlements.plist\"]"
            exit 1
            ;;
    esac
done

# Configuration
APP_NAME="YSocial"

# Read VERSION from file if it exists, otherwise use default
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
VERSION_FILE="${PROJECT_ROOT}/VERSION"

if [ -f "$VERSION_FILE" ]; then
    VERSION=$(cat "$VERSION_FILE" | tr -d '[:space:]')
else
    VERSION="${VERSION:-2.0.0}"
fi

DMG_NAME="${APP_NAME}-${VERSION}"
SOURCE_APP="dist/${APP_NAME}"
BACKGROUND_IMAGE="y_web/static/assets/img/installer/background.png"
ICON_FILE="images/YSocial_ico.png"

# Directories
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

# Copy uninstall script and user README to DMG
echo "📄 Adding uninstall script and README..."
if [ -f "$SCRIPT_DIR/uninstall.sh" ]; then
    cp "$SCRIPT_DIR/uninstall.sh" "$STAGING_DIR/Uninstall YSocial.command"
    chmod +x "$STAGING_DIR/Uninstall YSocial.command"
fi

if [ -f "$SCRIPT_DIR/uninstall_ysocial.py" ]; then
    cp "$SCRIPT_DIR/uninstall_ysocial.py" "$STAGING_DIR/.uninstall_ysocial.py"
    chmod +x "$STAGING_DIR/.uninstall_ysocial.py"
fi

if [ -f "$SCRIPT_DIR/README_USER.md" ]; then
    cp "$SCRIPT_DIR/README_USER.md" "$STAGING_DIR/README.md"
fi

# Sign the .app bundle if codesign identity is provided
if [ -n "$CODESIGN_IDENTITY" ]; then
    echo "🔐 Signing YSocial.app bundle..."
    CODESIGN_CMD="codesign --force --sign \"$CODESIGN_IDENTITY\" --timestamp --options runtime --deep"
    
    # Add entitlements if provided
    if [ -n "$ENTITLEMENTS_FILE" ]; then
        # Handle both absolute and relative paths
        if [ -f "$ENTITLEMENTS_FILE" ]; then
            CODESIGN_CMD="$CODESIGN_CMD --entitlements \"$ENTITLEMENTS_FILE\""
        elif [ -f "$PROJECT_ROOT/$ENTITLEMENTS_FILE" ]; then
            CODESIGN_CMD="$CODESIGN_CMD --entitlements \"$PROJECT_ROOT/$ENTITLEMENTS_FILE\""
        else
            echo "⚠️  Warning: Entitlements file not found: $ENTITLEMENTS_FILE"
        fi
    fi
    
    # Execute the signing command
    eval "$CODESIGN_CMD \"$APP_BUNDLE\""
    
    # Verify the signature
    codesign --verify --deep --verbose "$APP_BUNDLE"
    echo "✅ .app bundle signed successfully"
fi

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

# Verify the mount is writable
if [ ! -w "$MOUNT_DIR" ]; then
    echo "⚠️  Warning: Mounted DMG is not writable, remounting..."
    hdiutil detach "$DMG_DEVICE" 2>/dev/null || true
    sleep 2
    hdiutil attach -readwrite -noverify -noautoopen "$TEMP_DMG" | egrep '^/dev/' | sed 1q | awk '{print $1}' > /tmp/dmg_device.txt
    DMG_DEVICE=$(cat /tmp/dmg_device.txt)
    sleep 3
fi

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
        set icon size of viewOptions to 48
        set background picture of viewOptions to file ".background:background.png"

        -- Position icons (centered to align with arrow in background - 284x383 window)
        set position of item "YSocial.app" of container window to {180, 160}
        set position of item "Applications" of container window to {400, 160}

        -- Position additional files (smaller, at bottom)
        set position of item "README.md" of container window to {50, 330}
        set position of item "Uninstall YSocial.command" of container window to {500, 330}

        close
        open
        update without registering applications
        delay 15
    end tell
end tell
ASCRIPT

# Only apply AppleScript customization if background exists
if [ -f "$MOUNT_DIR/.background/background.png" ]; then
    osascript /tmp/dmg_customization.applescript || echo "⚠️  Warning: Could not apply visual customization"
    sleep 2
fi

# Set custom icon for DMG volume if available
MOUNTED_APP_BUNDLE="$MOUNT_DIR/YSocial.app"
if [ -f "$MOUNTED_APP_BUNDLE/Contents/Resources/YSocial.icns" ]; then
    echo "🎨 Setting DMG volume icon..."
    # Try to copy the icon, but don't fail if it doesn't work
    if cp "$MOUNTED_APP_BUNDLE/Contents/Resources/YSocial.icns" "$MOUNT_DIR/.VolumeIcon.icns" 2>/dev/null; then
        SetFile -c icnC "$MOUNT_DIR/.VolumeIcon.icns" 2>/dev/null || true
        SetFile -a C "$MOUNT_DIR" 2>/dev/null || true
        echo "   ✅ Volume icon set successfully"
    else
        echo "   ⚠️  Warning: Could not set volume icon (DMG will still work)"
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
