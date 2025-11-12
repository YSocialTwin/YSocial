# macOS Code Signing for YSocial PyInstaller Executable

This document explains how to properly code sign the YSocial PyInstaller executable for distribution on macOS.

## The Problem

When you build a PyInstaller single-file executable on macOS and run it on other machines, it may hang at the splash screen. This happens because:

1. **PyInstaller extracts to a temporary directory**: The single-file executable extracts its contents to `~/Library/Application Support/YSocial/_MEI<random>` at runtime
2. **macOS Gatekeeper blocks unsigned libraries**: On machines other than the build machine, macOS blocks the extracted unsigned libraries from loading
3. **Ad-hoc signing with `--deep` is insufficient**: The `--deep` flag doesn't properly sign nested components

## The Solution

YSocial now includes an `entitlements.plist` file that disables library validation for ad-hoc signed applications. This allows the executable to load its own extracted libraries.

### After Building with PyInstaller

After building the executable with `pyinstaller y_social.spec`, sign it with the entitlements file:

```bash
# For ad-hoc signing (testing and local distribution)
codesign --force --sign - \
  --entitlements entitlements.plist \
  --timestamp \
  --options runtime \
  dist/YSocial
```

**Important**: 
- DO NOT use the `--deep` flag (it's deprecated and doesn't work properly)
- The entitlements file is automatically embedded by PyInstaller, but you still need to sign the final executable
- Use `--options runtime` to enable Hardened Runtime

### For Production Distribution with Developer ID (Optional)

For wider distribution outside your organization, you can use a Developer ID certificate instead of ad-hoc signing:

```bash
# Automated (recommended)
./packaging/build_and_package_macos.sh --dev-id "Developer ID Application: Your Name"

# Or manually
codesign --force --sign "Developer ID Application: Your Name" \
  --entitlements entitlements.plist \
  --timestamp \
  --options runtime \
  dist/YSocial

# Verify the signing
codesign --verify --deep --strict --verbose=2 dist/YSocial

# Check the entitlements
codesign -d --entitlements - dist/YSocial
```

**When to use Developer ID:**
- Distributing to users outside your organization
- Want to avoid Gatekeeper security warnings
- Planning to notarize the app with Apple

**When ad-hoc signing is sufficient:**
- Testing and development
- Internal distribution within your organization
- Users can bypass Gatekeeper (right-click → Open)

### Automated Build and Package Script

The easiest way to build, sign, and package YSocial is to use the automated script:

```bash
# With ad-hoc signing (recommended for testing and local distribution)
./packaging/build_and_package_macos.sh

# Or with Developer ID for wider distribution
./packaging/build_and_package_macos.sh --dev-id "Developer ID Application: Your Name"
```

This script automatically:
1. Builds the executable with PyInstaller
2. Signs the executable with entitlements
3. Creates the DMG installer
4. Signs the .app bundle inside the DMG

### Manual Build and Package Process

If you prefer to run the steps manually:

```bash
# 1. Build the executable
pyinstaller y_social.spec --clean --noconfirm

# 2. Sign the executable before bundling
codesign --force --sign - \
  --entitlements entitlements.plist \
  --timestamp \
  --options runtime \
  dist/YSocial

# 3. Create the DMG (which will copy the signed executable into the .app bundle)
./packaging/create_dmg.sh

# 4. Sign the .app bundle inside the DMG
# Mount the DMG, sign the .app, then unmount
hdiutil attach dist/YSocial-*.dmg -mountpoint /Volumes/YSocial -nobrowse
codesign --force --sign - \
  --entitlements entitlements.plist \
  --timestamp \
  --options runtime \
  --deep \
  /Volumes/YSocial/YSocial.app
hdiutil detach /Volumes/YSocial
```

**Note**: For production distribution with a Developer ID certificate, replace `--sign -` with `--sign "Developer ID Application: Your Name"`

## What the Entitlements Do

The `entitlements.plist` file includes these key permissions:

- **`com.apple.security.cs.disable-library-validation`**: Allows the app to load libraries that aren't signed with the same certificate
- **`com.apple.security.cs.allow-unsigned-executable-memory`**: Allows Python's bytecode execution
- **`com.apple.security.cs.allow-dyld-environment-variables`**: Allows dynamic library loading
- **`com.apple.security.cs.allow-jit`**: Allows Just-In-Time compilation (needed for some Python packages)

These entitlements are necessary for PyInstaller single-file executables because the extracted libraries won't have the same signature as the main executable.

## Verification

After signing, verify the executable works:

```bash
# Check signature
codesign --verify --verbose dist/YSocial

# Display signature details
codesign -dvv dist/YSocial

# Check entitlements
codesign -d --entitlements - dist/YSocial

# Test on another machine
# Copy dist/YSocial to another macOS machine and run it
```

## Notarization (Optional but Recommended)

For distribution outside the App Store, notarize your app:

```bash
# 1. Create a ZIP of the signed executable
ditto -c -k --keepParent dist/YSocial YSocial.zip

# 2. Submit for notarization
xcrun notarytool submit YSocial.zip \
  --apple-id "your-email@example.com" \
  --team-id "YOUR_TEAM_ID" \
  --password "app-specific-password" \
  --wait

# 3. Staple the notarization ticket
xcrun stapler staple dist/YSocial

# 4. Verify notarization
xcrun stapler validate dist/YSocial
```

## Common Issues and Solutions

### "Code signing blocked"
**Problem**: macOS blocks the app from running on other machines.

**Solution**: Sign with the entitlements file using the commands above.

### "The executable has been modified"
**Problem**: The signature is broken after modifying the file.

**Solution**: Re-sign after any modifications.

### "Killed: 9" when running the app
**Problem**: macOS killed the app due to signature issues.

**Solution**: 
1. Check signature: `codesign --verify --verbose dist/YSocial`
2. Re-sign with entitlements if verification fails

### App hangs at splash screen on other machines
**Problem**: Libraries are being blocked from loading.

**Solution**: 
1. Ensure you signed with the entitlements file
2. Verify entitlements are embedded: `codesign -d --entitlements - dist/YSocial`
3. Check for "com.apple.security.cs.disable-library-validation" in the output

## Why One-File Mode?

YSocial uses PyInstaller's **one-file mode** for distribution, which provides:

- **Simple distribution**: Single executable file, easy to download and share
- **No dependencies**: Everything bundled in one file
- **User-friendly**: No complex folder structures to manage
- **Smaller download size**: Compared to bundling all files separately

The entitlements approach allows one-file mode to work correctly on all macOS machines without switching to the more complex onedir mode.

## Summary

The key changes to fix the hanging issue:

1. **Added `entitlements.plist`**: Disables library validation for ad-hoc signed apps
2. **Updated `y_social.spec`**: References the entitlements file
3. **Updated signing procedure**: Use entitlements when signing the executable

After building, always sign with:
```bash
codesign --force --sign - \
  --entitlements entitlements.plist \
  --timestamp \
  --options runtime \
  dist/YSocial
```

This allows the PyInstaller executable to load its extracted libraries on any macOS machine.
