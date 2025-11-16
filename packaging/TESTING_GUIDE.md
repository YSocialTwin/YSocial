# Multi-File Packaging Testing Guide

This document provides step-by-step instructions for testing the multi-file PyInstaller packaging migration.

## Pre-Testing Setup

### 1. Install Dependencies

```bash
# Install Python dependencies
pip install -r requirements.txt

# Install PyInstaller
pip install pyinstaller

# Download NLTK data
python -c "import nltk; nltk.download('vader_lexicon')"

# Create config directory
mkdir -p config_files

# Initialize git submodules
git submodule update --init --recursive
```

### 2. Run Validation Script

```bash
# Validate that migration was done correctly
python validate_multifile_packaging.py
```

Expected output: All checks should pass ✅

---

## Build Testing

### Test 1: Clean Build

**Objective**: Verify PyInstaller creates multi-file directory structure

```bash
# Clean previous builds
rm -rf build/ dist/

# Build with PyInstaller
pyinstaller y_social.spec --clean --noconfirm

# Verify output structure
ls -la dist/
```

**Expected Results**:
- ✅ `dist/YSocial/` directory exists (not `dist/YSocial` file)
- ✅ `dist/YSocial/YSocial` executable exists
- ✅ Multiple `.dylib` or `.so` files in directory (macOS/Linux)
- ✅ Multiple `.pyd` and `.dll` files (Windows)
- ✅ `_internal/` subdirectory with PyInstaller internals
- ✅ Data files present (templates, static, config, etc.)

### Test 2: Directory Size and Content

```bash
# Check directory size
du -sh dist/YSocial/

# Count files
find dist/YSocial -type f | wc -l

# List major components
ls -lh dist/YSocial/ | head -20
```

**Expected Results**:
- ✅ Total size: ~500MB-1GB (similar to old single-file)
- ✅ 500+ files (dependencies, libraries, data files)
- ✅ Executable file is relatively small (~5-10MB)
- ✅ Most size in library files and data

---

## Functional Testing

### Test 3: Basic Launch (All Platforms)

**Linux/macOS**:
```bash
cd dist/YSocial
./YSocial --help
```

**Windows**:
```cmd
cd dist\YSocial
YSocial.exe --help
```

**Expected Results**:
- ✅ Help message displays immediately
- ✅ No extraction/decompression delay
- ✅ Command line options listed correctly
- ✅ Process exits cleanly

### Test 4: Application Startup

**Desktop Mode (Default)**:
```bash
cd dist/YSocial
./YSocial
```

**Browser Mode**:
```bash
cd dist/YSocial
./YSocial --browser
```

**Expected Results**:
- ✅ Application starts within 2-5 seconds (much faster than single-file)
- ✅ Desktop window opens (desktop mode) or browser launches (browser mode)
- ✅ Login page displays correctly
- ✅ CSS/JS/images load properly
- ✅ No console errors in browser developer tools

### Test 5: Resource Access

1. **Login with default credentials**:
   - Email: `admin@ysocial.com`
   - Password: `test`

2. **Check admin interface**:
   - ✅ Admin dashboard loads
   - ✅ Navigation works
   - ✅ Static assets (images, CSS) display correctly

3. **Create a simple experiment**:
   - ✅ Form displays properly
   - ✅ Database operations work
   - ✅ Data persists after restart

### Test 6: Path Resolution

**Create test script** (`test_paths.py`):
```python
import sys
sys.path.insert(0, '.')

from y_web.utils.path_utils import get_base_path, get_resource_path, get_writable_path

print(f"Base path: {get_base_path()}")
print(f"Resource path (data_schema): {get_resource_path('data_schema')}")
print(f"Writable path: {get_writable_path()}")

import os
print(f"Base path exists: {os.path.exists(get_base_path())}")
print(f"Data schema exists: {os.path.exists(get_resource_path('data_schema'))}")
print(f"Writable path exists: {os.path.exists(get_writable_path())}")
```

Run from within the bundle:
```bash
cd dist/YSocial
./YSocial -c "exec(open('../../test_paths.py').read())"  # or similar
```

**Expected Results**:
- ✅ Base path points to `dist/YSocial/`
- ✅ Resource paths resolve correctly
- ✅ Writable path points to user directory (not installation dir)
- ✅ All paths exist

---

## Performance Testing

### Test 7: Startup Time Comparison

**Method 1: Using time command**:
```bash
# Multi-file build
time dist/YSocial/YSocial --help

# Compare with old single-file if available
time dist_old/YSocial --help
```

**Method 2: Measure to first response**:
```bash
# Start app and time until server responds
time bash -c "dist/YSocial/YSocial --browser --no-browser & sleep 5; curl -s http://localhost:8080 > /dev/null; pkill -f YSocial"
```

**Expected Results**:
- ✅ Multi-file startup 30-70% faster than single-file
- ✅ `--help` responds in <1 second
- ✅ Full application start in 2-5 seconds
- ✅ No noticeable extraction delays

### Test 8: Memory Usage

```bash
# Start application
dist/YSocial/YSocial --browser &
PID=$!

# Monitor memory usage
ps aux | grep YSocial
# or on macOS
ps -o rss,vsz -p $PID

# Wait for startup to complete
sleep 10

# Check peak memory
ps aux | grep YSocial

# Cleanup
kill $PID
```

**Expected Results**:
- ✅ Initial memory usage lower than single-file
- ✅ Memory grows as resources are loaded (on-demand)
- ✅ No sudden large allocations (extraction)

---

## Platform-Specific Testing

### macOS Tests

#### Test 9: Code Signing Verification

```bash
# Check if executable is signed
codesign -dv --verbose=4 dist/YSocial/YSocial

# Verify signature
codesign --verify --deep --strict --verbose=2 dist/YSocial/YSocial

# Check entitlements
codesign -d --entitlements - dist/YSocial/YSocial

# Test all libraries are signed
find dist/YSocial -type f \( -name "*.dylib" -o -name "*.so" \) | while read lib; do
    echo "Checking: $lib"
    codesign -dv "$lib" 2>&1 | head -3
done
```

**Expected Results**:
- ✅ Main executable has valid signature
- ✅ Entitlements include required keys (disable-library-validation, etc.)
- ✅ All `.dylib` and `.so` files are signed
- ✅ No "unsigned" warnings

#### Test 10: App Bundle Creation

```bash
# Run DMG creation script
./packaging/create_dmg.sh --codesign-identity "-"

# Check output
ls -lh dist/*.dmg

# Mount and inspect DMG
hdiutil attach dist/YSocial-*.dmg
ls -la /Volumes/YSocial/
```

**Expected Results**:
- ✅ DMG created successfully
- ✅ DMG contains `YSocial.app`
- ✅ `.app` bundle has proper structure
- ✅ Can drag to Applications folder
- ✅ Launches from Applications folder

#### Test 11: Gatekeeper Test

```bash
# Test if macOS allows execution
spctl --assess --type execute -vv dist/YSocial/YSocial

# If properly signed, should see:
# dist/YSocial/YSocial: accepted
```

**Expected Results** (with proper signing):
- ✅ `accepted` status
- ✅ No Gatekeeper warnings
- ✅ App runs on different Mac without warnings

### Windows Tests

#### Test 12: Console Window

```bash
# Start application
dist\YSocial\YSocial.exe
```

**Expected Results**:
- ✅ No console window appears (console=False in spec)
- ✅ Desktop window or browser opens directly
- ✅ Can check logs in `%LOCALAPPDATA%\YSocial\ysocial.log`

#### Test 13: Antivirus Scan

```bash
# Run Windows Defender scan (or your AV)
# Right-click on dist\YSocial and select "Scan with Microsoft Defender"
```

**Expected Results**:
- ✅ No threats detected
- ✅ All files pass scan
- ⚠️ If flagged, may need to submit as false positive

### Linux Tests

#### Test 14: Dependencies Check

```bash
# Check shared library dependencies
ldd dist/YSocial/YSocial

# Verify all dependencies are bundled or available
ldd dist/YSocial/_internal/*.so | grep "not found"
```

**Expected Results**:
- ✅ All required `.so` files found
- ✅ No "not found" errors
- ✅ System libraries available (libc, libm, etc.)

#### Test 15: Desktop Integration

```bash
# Create desktop entry
cat > ~/.local/share/applications/ysocial.desktop << EOF
[Desktop Entry]
Type=Application
Name=YSocial
Exec=/path/to/dist/YSocial/YSocial
Icon=/path/to/images/YSocial_ico.png
Terminal=false
Categories=Network;WebApplication;
EOF

# Test launch from application menu
```

**Expected Results**:
- ✅ Appears in application menu
- ✅ Launches correctly from menu
- ✅ Icon displays if provided

---

## Regression Testing

### Test 16: Subprocess Launches

1. Create a test experiment in admin panel
2. Configure with at least one client
3. Start the simulation
4. Verify:
   - ✅ Server subprocess starts
   - ✅ Client subprocess starts
   - ✅ Subprocesses can access resources
   - ✅ Inter-process communication works
   - ✅ Database updates reflect simulation activity

### Test 17: File Operations

1. Create experiment with database
2. Import/export functionality (if available)
3. Configuration file operations
4. Verify:
   - ✅ Files written to correct locations (user directories)
   - ✅ No permission errors
   - ✅ Files persist after restart

---

## Automated Testing (if pytest available)

```bash
# Install test dependencies
pip install pytest pytest-flask

# Run test suite
pytest y_web/tests/ -v

# Specific PyInstaller tests
pytest y_web/tests/test_pyinstaller_console_suppression.py -v
pytest y_web/tests/test_pyinstaller_server_subprocess.py -v
```

**Expected Results**:
- ✅ All tests pass
- ✅ No new failures compared to main branch
- ✅ PyInstaller-specific tests pass

---

## Rollback Testing

### Test 18: Verify Rollback Works

```bash
# Save current spec
cp y_social.spec y_social.spec.multifile

# Simulate rollback (don't actually commit)
git show HEAD~2:y_social.spec > y_social.spec.singlefile

# Try building with old spec
pyinstaller y_social.spec.singlefile --clean --noconfirm

# Verify single-file output
ls -l dist/

# Restore multi-file spec
cp y_social.spec.multifile y_social.spec
```

**Expected Results**:
- ✅ Old spec produces single file `dist/YSocial`
- ✅ Can switch back if needed
- ✅ Rollback process is documented

---

## Sign-Off Checklist

Before marking migration complete, verify:

### Critical Tests
- [ ] Application builds without errors
- [ ] Output is a directory (not single file)
- [ ] Application launches successfully
- [ ] Startup time is noticeably faster
- [ ] All resources accessible (CSS, JS, templates)
- [ ] User login works
- [ ] Database operations work
- [ ] Application can be restarted

### Platform-Specific (macOS)
- [ ] All libraries are signed
- [ ] Main executable signed with entitlements
- [ ] DMG creation works
- [ ] .app bundle structure correct
- [ ] Can drag-drop to Applications
- [ ] Launches from Applications folder

### Platform-Specific (Windows)
- [ ] No console window appears
- [ ] All DLLs present
- [ ] Antivirus doesn't flag

### Platform-Specific (Linux)
- [ ] All .so files present
- [ ] No missing dependencies
- [ ] Desktop integration possible

### Documentation
- [ ] BUILD_EXECUTABLES.md updated
- [ ] MULTIFILE_MIGRATION.md created
- [ ] GitHub Actions updated
- [ ] README mentions multi-file

### Validation
- [ ] validate_multifile_packaging.py passes
- [ ] Shell scripts validate (bash -n)
- [ ] Spec file valid Python syntax

---

## Troubleshooting Common Issues

### Issue: "dist/YSocial is a file, not directory"
**Solution**: Clean build and rebuild with new spec:
```bash
rm -rf build/ dist/
pyinstaller y_social.spec --clean --noconfirm
```

### Issue: "Library not loaded" on macOS
**Solution**: Sign all libraries:
```bash
find dist/YSocial -type f \( -name "*.dylib" -o -name "*.so" \) -exec codesign --force --sign - --options runtime {} \;
codesign --force --sign - --entitlements packaging/entitlements.plist --options runtime dist/YSocial/YSocial
```

### Issue: Slow startup still
**Cause**: Might be disk I/O, not extraction
**Check**: Run with time command and compare to single-file build

### Issue: "Permission denied" on files
**Solution**: 
```bash
chmod +x dist/YSocial/YSocial
chmod -R u+r dist/YSocial/
```

### Issue: DMG creation fails
**Solution**: Check that dist/YSocial directory exists before running create_dmg.sh

---

## Performance Benchmarks

Record these for comparison:

| Metric | Single-File | Multi-File | Improvement |
|--------|-------------|------------|-------------|
| Build time | ___ sec | ___ sec | ___ |
| Startup time (--help) | ___ sec | ___ sec | ___ |
| Full startup | ___ sec | ___ sec | ___ |
| Memory (peak) | ___ MB | ___ MB | ___ |
| Disk size (uncompressed) | ___ MB | ___ MB | ___ |
| Disk size (compressed) | ___ MB | ___ MB | ___ |

---

## Reporting Results

When reporting test results, include:

1. **Platform**: macOS/Windows/Linux version
2. **Python version**: Output of `python --version`
3. **PyInstaller version**: Output of `pyinstaller --version`
4. **Test results**: Pass/fail for each test
5. **Performance metrics**: Startup time comparison
6. **Issues found**: Any problems encountered
7. **Screenshots**: For UI-related issues

---

## Next Steps After Testing

If all tests pass:
1. ✅ Merge PR
2. ✅ Tag release
3. ✅ Update release notes
4. ✅ Rebuild all platform executables
5. ✅ Upload to release page
6. ✅ Update documentation website

If issues found:
1. Document the issue
2. Determine severity (blocker vs minor)
3. Fix if needed or rollback
4. Re-test
5. Update documentation with findings
