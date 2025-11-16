# PyInstaller Multi-File Packaging Migration Guide

This document details the migration from single-file (onefile) to multi-file (onedir) PyInstaller packaging for YSocial.

## Executive Summary

**What Changed**: YSocial now uses PyInstaller's multi-file (onedir) packaging mode instead of single-file (onefile) mode.

**Why**: Single-file executables extract all resources to a temporary directory at startup, causing slow application launch times. Multi-file packaging eliminates this extraction step, resulting in significantly faster startup.

**Impact**: 
- ✅ **Faster startup** - Resources are accessed directly, no extraction needed
- ✅ **Lower memory footprint** - Resources loaded on-demand
- ✅ **Easier debugging** - Individual files can be inspected
- ✅ **Better code signing** - Each library signed individually on macOS
- ⚠️ **Distribution change** - Application is now a directory instead of a single file

---

## Technical Changes

### 1. PyInstaller Spec File (`y_social.spec`)

**Before (Single-File Mode)**:
```python
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,    # All binaries bundled in executable
    a.zipfiles,    # All zip files bundled in executable
    a.datas,       # All data files bundled in executable
    [],
    name="YSocial",
    ...
)
```

**After (Multi-File Mode)**:
```python
exe = EXE(
    pyz,
    a.scripts,
    [],
    name="YSocial",
    ...
)

# COLLECT step creates directory structure
coll = COLLECT(
    exe,
    a.binaries,    # Binaries placed in directory
    a.zipfiles,    # Zip files placed in directory
    a.datas,       # Data files placed in directory
    strip=False,
    upx=True,
    upx_exclude=[],
    name="YSocial",
)
```

**What This Means**:
- **Single-file**: PyInstaller creates `dist/YSocial` (executable file) that extracts to temp directory at runtime
- **Multi-file**: PyInstaller creates `dist/YSocial/` (directory) with `YSocial` executable and all dependencies

### 2. Path Handling (`y_web/utils/path_utils.py`)

The `sys._MEIPASS` variable behavior changes:

**Single-File Mode**:
- `sys._MEIPASS` → Temporary extraction directory (e.g., `/tmp/_MEIxxxxxx`)
- Extracted on every launch to a new temp directory
- Cleaned up when app exits

**Multi-File Mode**:
- `sys._MEIPASS` → The `dist/YSocial/` directory itself
- Resources accessed directly from installation location
- No extraction, no cleanup needed

**Code Update**: Updated comments in `get_base_path()` to clarify both modes are supported.

### 3. macOS Code Signing (`packaging/build_and_package_macos.sh`)

**Key Changes**:
1. Check for directory `dist/YSocial/` instead of file `dist/YSocial`
2. Sign all `.dylib` and `.so` files individually before signing main executable
3. Sign main executable `dist/YSocial/YSocial` (not `dist/YSocial`)

**Why This Matters**:
- macOS requires all dynamic libraries to be signed for Hardened Runtime
- Multi-file mode exposes these libraries as separate files
- Proper signing prevents "library validation" errors

**Signing Process**:
```bash
# 1. Sign all dependencies first
find dist/YSocial -type f \( -name "*.dylib" -o -name "*.so" \) \
  -exec codesign --force --sign "$IDENTITY" --options runtime {} \;

# 2. Sign main executable with entitlements
codesign --force --sign "$IDENTITY" \
  --entitlements packaging/entitlements.plist \
  --options runtime \
  dist/YSocial/YSocial
```

### 4. DMG Creation (`packaging/create_dmg.sh`)

**Key Changes**:
1. Check for directory `dist/YSocial/` instead of file `dist/YSocial`
2. Copy entire directory contents to `.app/Contents/MacOS/`
3. Updated output structure

**Before**:
```
YSocial.app/
├── Contents/
│   ├── MacOS/
│   │   └── YSocial         (single executable file)
│   ├── Resources/
│   │   └── YSocial.icns
│   └── Info.plist
```

**After**:
```
YSocial.app/
├── Contents/
│   ├── MacOS/
│   │   ├── YSocial         (main executable)
│   │   ├── *.dylib         (dynamic libraries)
│   │   ├── *.so            (Python extensions)
│   │   ├── _internal/      (PyInstaller internals)
│   │   └── [other files]   (data files, resources)
│   ├── Resources/
│   │   └── YSocial.icns
│   └── Info.plist
```

**Critical**: The `.app` bundle still appears as a single draggable file to users. The multi-file structure is internal to the bundle.

---

## Testing Requirements

### Functional Testing

**Test 1: Basic Launch**
- [ ] Application launches without errors
- [ ] Startup time is noticeably faster than before
- [ ] No extraction delays observed
- [ ] Desktop mode opens properly
- [ ] Browser mode (with `--browser` flag) works

**Test 2: Resource Access**
- [ ] Static files (CSS, JS, images) load correctly
- [ ] Templates render properly
- [ ] Database schemas are accessible
- [ ] Configuration files are found
- [ ] NLTK data is available

**Test 3: Subprocess Execution**
- [ ] Client subprocess launches successfully
- [ ] Server subprocess starts properly
- [ ] Subprocess can access bundled resources
- [ ] Inter-process communication works

**Test 4: Path Resolution**
- [ ] `get_base_path()` returns correct directory
- [ ] `get_resource_path()` finds bundled files
- [ ] `get_writable_path()` creates user directories
- [ ] Relative paths resolve correctly

### Platform-Specific Testing

**macOS**:
- [ ] `.app` bundle launches from Finder
- [ ] Dragging to Applications folder works
- [ ] Code signature is valid (`codesign --verify`)
- [ ] Entitlements are applied correctly
- [ ] Gatekeeper accepts the signed app
- [ ] No "unidentified developer" warnings (with proper signing)
- [ ] DMG mounts and displays correctly
- [ ] Drag-and-drop installation works

**Windows**:
- [ ] Executable launches from Explorer
- [ ] No console window appears (console=False)
- [ ] Antivirus doesn't flag as malware
- [ ] All DLLs load correctly
- [ ] Splash screen displays (Windows only)

**Linux**:
- [ ] Executable runs from file manager
- [ ] Required .so files are found
- [ ] Desktop mode works (or gracefully falls back to browser)
- [ ] GTK dependencies handled properly

### Performance Testing

**Startup Time Comparison**:
1. Measure startup time with old single-file build
2. Measure startup time with new multi-file build
3. Expected improvement: 30-70% faster startup

**Memory Usage**:
1. Monitor memory during startup (old vs new)
2. Expected: Lower peak memory usage with multi-file

### Regression Testing

Run existing test suite to ensure no functionality broken:
```bash
# Run all tests
python -m pytest

# Run PyInstaller-specific tests
python -m pytest y_web/tests/test_pyinstaller_console_suppression.py
python -m pytest y_web/tests/test_pyinstaller_server_subprocess.py
```

---

## Critical Aspects & Gotchas

### 1. Distribution Format Change

**Critical**: Users now receive a **directory** instead of a **single file**.

**For macOS**: No issue - the `.app` bundle is still a single draggable icon
**For Windows**: Consider creating an installer (NSIS, Inno Setup) to hide the directory structure
**For Linux**: Consider packaging as `.deb`, `.rpm`, or AppImage for easier distribution

### 2. File Permissions

**Issue**: All files in `dist/YSocial/` need appropriate permissions
**Solution**: 
- Executable: `chmod +x dist/YSocial/YSocial`
- Data files: readable by owner
- DMG creation script handles this automatically

### 3. Code Signing on macOS

**Critical**: With multi-file mode, each `.dylib` and `.so` must be signed individually.

**Wrong Approach**:
```bash
# This signs only the main executable, not dependencies
codesign --sign "$IDENTITY" dist/YSocial/YSocial
```

**Correct Approach**:
```bash
# Sign all dependencies first
find dist/YSocial -type f \( -name "*.dylib" -o -name "*.so" \) \
  -exec codesign --force --sign "$IDENTITY" --options runtime {} \;

# Then sign main executable
codesign --force --sign "$IDENTITY" \
  --entitlements packaging/entitlements.plist \
  --options runtime \
  dist/YSocial/YSocial
```

**Why**: macOS Hardened Runtime validates all loaded libraries. Unsigned libraries cause app launch failure.

### 4. Relative Path Issues

**Issue**: Code that assumes single-file extraction to temp directory may break
**Check For**:
- Hard-coded paths to temp directories
- Code that expects clean temp dir on startup
- File locking issues (single-file could write to temp, multi-file cannot write to installation dir)

**Solution**: Use `get_writable_path()` for user data, `get_resource_path()` for bundled read-only data

### 5. Subprocess Invocation

**Issue**: When launching Python subprocesses, `sys.executable` behavior changes

**Single-File**: `sys.executable` → temporary executable (e.g., `/tmp/_MEIxxxxx/YSocial`)
**Multi-File**: `sys.executable` → installation directory executable (e.g., `dist/YSocial/YSocial`)

**Impact**: Subprocesses launched with `sys.executable` will work correctly in both modes, but paths differ

**Verification**: Test client and server subprocess launches thoroughly

### 6. File Size Considerations

**Multi-File vs Single-File**:
- Multi-file total size: ~Same as single-file
- Multi-file disk usage: Might be slightly higher due to file system overhead
- Multi-file compressed (DMG/ZIP): Nearly identical to single-file compressed

**Distribution**: For downloads, compress the directory. DMG (macOS) and ZIP (Windows/Linux) work well.

### 7. Notarization (macOS)

**Before Notarizing**:
1. Sign all individual files (`.dylib`, `.so`)
2. Sign main executable with entitlements
3. Sign `.app` bundle with `--deep` flag
4. Package into signed DMG
5. Submit DMG for notarization

**Command**:
```bash
# After creating YSocial.app
codesign --deep --force --sign "$IDENTITY" \
  --options runtime \
  --entitlements packaging/entitlements.plist \
  YSocial.app

# Create and sign DMG
# Then submit for notarization
xcrun notarytool submit YSocial-2.x.x.dmg \
  --keychain-profile "AC_PASSWORD" \
  --wait
```

---

## Rollback Plan

If critical issues are found, you can rollback to single-file mode:

1. **Edit `y_social.spec`**:
   - Move `a.binaries`, `a.zipfiles`, `a.datas` back into `EXE()`
   - Remove the `COLLECT()` step

2. **Revert packaging scripts**:
   ```bash
   git checkout origin/main packaging/build_and_package_macos.sh
   git checkout origin/main packaging/create_dmg.sh
   ```

3. **Rebuild**:
   ```bash
   pyinstaller y_social.spec --clean --noconfirm
   ```

4. **Result**: Single file at `dist/YSocial` instead of directory `dist/YSocial/`

---

## Benefits Summary

| Aspect | Single-File (Before) | Multi-File (After) |
|--------|---------------------|-------------------|
| Startup Time | Slow (extraction delay) | Fast (direct access) |
| Memory Usage | Higher (full extraction) | Lower (on-demand) |
| Distribution | Single file | Directory (but .app on macOS) |
| Debugging | Difficult | Easier (inspect files) |
| Code Signing | Single signature | Per-file signatures |
| Disk Space | Temporary + Permanent | Permanent only |
| File Access | Copy to temp | Direct from install dir |

---

## References

- [PyInstaller Documentation - Onefile vs Onedir](https://pyinstaller.org/en/stable/operating-mode.html)
- [Apple Code Signing Guide](https://developer.apple.com/library/archive/documentation/Security/Conceptual/CodeSigningGuide/)
- [YSocial Code Signing Documentation](../MACOS_CODE_SIGNING.md)

---

## Change Log

**Date**: 2025-11-16
**Version**: 2.x.x
**Author**: Copilot Agent
**Status**: Implemented and Documented

**Files Modified**:
- `y_social.spec` - Added COLLECT() for multi-file packaging
- `y_web/utils/path_utils.py` - Updated comments for clarity
- `packaging/build_and_package_macos.sh` - Updated for directory handling and library signing
- `packaging/create_dmg.sh` - Updated to copy directory contents to .app bundle
- `packaging/BUILD_EXECUTABLES.md` - Updated documentation
- `packaging/MULTIFILE_MIGRATION.md` - This file (new)

**Files Verified Compatible** (no changes needed):
- `y_social_launcher.py` - sys.frozen and sys._MEIPASS handling works for both modes
- `y_web/pyinstaller_utils/y_social_launcher.py` - Path handling compatible
- `y_web/utils/external_processes.py` - Subprocess execution compatible
- All other `_MEIPASS` references - Compatible with both modes
