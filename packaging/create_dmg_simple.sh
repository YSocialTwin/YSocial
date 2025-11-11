#!/bin/bash
# Alternative DMG creation script using create-dmg tool
# This requires the create-dmg tool: brew install create-dmg
#
# This is an easier alternative to create_dmg.sh that handles most
# of the complexity automatically

set -e

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
FINAL_DMG="${PROJECT_ROOT}/dist/${DMG_NAME}.dmg"

# Check if we're on macOS
if [[ "$OSTYPE" != "darwin"* ]]; then
    echo "❌ Error: This script must be run on macOS"
    exit 1
fi

# Check if create-dmg is installed
if ! command -v create-dmg &> /dev/null; then
    echo "❌ Error: create-dmg is not installed"
    echo "Please install it with: brew install create-dmg"
    exit 1
fi

# Check if source app exists
if [ ! -f "$PROJECT_ROOT/$SOURCE_APP" ]; then
    echo "❌ Error: YSocial executable not found at $PROJECT_ROOT/$SOURCE_APP"
    echo "Please build the executable first using: pyinstaller y_social.spec"
    exit 1
fi

echo "🚀 Creating YSocial DMG installer using create-dmg..."
echo "   Version: $VERSION"

# Clean up
rm -rf "$STAGING_DIR"
rm -f "$FINAL_DMG"
mkdir -p "$STAGING_DIR"
mkdir -p "$(dirname "$FINAL_DMG")"

# Create .app bundle
echo "📦 Creating YSocial.app bundle..."
APP_BUNDLE="$STAGING_DIR/${APP_NAME}.app"
mkdir -p "$APP_BUNDLE/Contents/MacOS"
mkdir -p "$APP_BUNDLE/Contents/Resources"

# Copy executable
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

# Convert icon to .icns if available
if [ -f "$PROJECT_ROOT/$ICON_FILE" ]; then
    echo "🎨 Converting icon..."
    if command -v sips &> /dev/null && command -v iconutil &> /dev/null; then
        ICONSET_DIR="$STAGING_DIR/YSocial.iconset"
        mkdir -p "$ICONSET_DIR"
        
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
        
        iconutil -c icns "$ICONSET_DIR" -o "$APP_BUNDLE/Contents/Resources/YSocial.icns"
        rm -rf "$ICONSET_DIR"
    fi
fi

# Create DMG using create-dmg tool
echo "💿 Creating DMG..."

# Prepare background if available
BACKGROUND_ARG=""
if [ -f "$PROJECT_ROOT/$BACKGROUND_IMAGE" ]; then
    BACKGROUND_ARG="--background $PROJECT_ROOT/$BACKGROUND_IMAGE"
fi

# Icon argument if available
ICON_ARG=""
if [ -f "$APP_BUNDLE/Contents/Resources/YSocial.icns" ]; then
    ICON_ARG="--icon-size 128 --icon $APP_BUNDLE/Contents/Resources/YSocial.icns"
fi

create-dmg \
    --volname "$APP_NAME" \
    --volicon "$APP_BUNDLE/Contents/Resources/YSocial.icns" \
    $BACKGROUND_ARG \
    --window-pos 200 120 \
    --window-size 568 766 \
    --icon-size 128 \
    --icon "${APP_NAME}.app" 100 320 \
    --hide-extension "${APP_NAME}.app" \
    --app-drop-link 420 320 \
    "$FINAL_DMG" \
    "$STAGING_DIR"

# Clean up
rm -rf "$STAGING_DIR"

echo ""
echo "✅ DMG created successfully!"
echo "   Location: $FINAL_DMG"
echo "   Size: $(du -h "$FINAL_DMG" | cut -f1)"
