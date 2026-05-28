# PyInstaller Packaging

## Purpose

YSocial supports PyInstaller-based packaging for desktop distribution. The packaged application uses:

- `/Users/rossetti/PycharmProjects/YWeb/y_social.spec`
- `/Users/rossetti/PycharmProjects/YWeb/y_social_launcher.py`
- helper modules under `/Users/rossetti/PycharmProjects/YWeb/y_web/pyinstaller_utils/`

The packaging flow bundles:

- application code
- templates and static files
- selected external runtime assets
- database schemas and config files
- platform-specific desktop launcher behavior

## General prerequisites

Before building on any platform:

```bash
git clone https://github.com/YSocialTwin/YSocial.git
cd YSocial
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install pyinstaller
```

Also ensure the required runtime repositories are cloned under `external/`:

```bash
python -c "import nltk; nltk.download('vader_lexicon')"
```

## Core build command

All platforms start from the same spec-based build:

```bash
pyinstaller y_social.spec --clean --noconfirm
```

Build output:

- macOS/Linux: `dist/YSocial`
- Windows: `dist/YSocial.exe`

## Platform-specific guidance

### macOS

macOS requires the most explicit post-build handling.

Recommended path:

```bash
./packaging/build_and_package_macos.sh
```

This covers:

1. PyInstaller build
2. code signing
3. DMG creation
4. app bundle preparation

Manual path:

```bash
pyinstaller y_social.spec --clean --noconfirm
codesign --force --sign - \
  --entitlements packaging/entitlements.plist \
  --timestamp \
  --options runtime \
  dist/YSocial
./packaging/create_dmg.sh --codesign-identity "-" --entitlements packaging/entitlements.plist
```

For broader distribution, replace ad-hoc signing with a Developer ID workflow and, if needed, notarization.

Reference:

- `/Users/rossetti/PycharmProjects/YWeb/docs/MACOS_CODE_SIGNING.md`

### Linux

Linux packaging is simpler operationally:

```bash
pyinstaller y_social.spec --clean --noconfirm
```

Practical notes:

- build on a reasonably common target environment for better compatibility
- GUI dependencies may still matter if desktop mode is used
- browser mode is often the safer default on headless or server-oriented Linux deployments

Typical distribution artifact:

- tarball containing `dist/YSocial`

### Windows

Windows also uses the same spec build:

```bash
pyinstaller y_social.spec --clean --noconfirm
```

Typical notes:

- output is `dist/YSocial.exe`
- SmartScreen or antivirus false positives may occur for unsigned builds
- test both desktop mode and browser mode after building

## What the spec file includes

The current spec file bundles:

- `/Users/rossetti/PycharmProjects/YWeb/y_web/static`
- `/Users/rossetti/PycharmProjects/YWeb/y_web/templates`
- `/Users/rossetti/PycharmProjects/YWeb/data_schema`
- `/Users/rossetti/PycharmProjects/YWeb/config_files`
- `/Users/rossetti/PycharmProjects/YWeb/images`
- `/Users/rossetti/PycharmProjects/YWeb/VERSION`
- selected runner scripts and notebook assets
- selected external runtime repositories when present

## Packaging constraints to know

### Notebook support

PyInstaller mode disables the normal notebook workflow by design. Packaged builds should not be treated as full notebook-authoring environments.

### Desktop mode

Desktop mode depends on `pywebview` and, on some platforms, additional GUI system libraries.

### Single-file behavior

The build is single-file oriented. Resources are extracted at runtime to temporary locations, but user data is still stored in runtime directories outside the extracted bundle.

## Validation checklist after building

1. run `--help`
2. start in desktop mode
3. start in browser mode
4. log in to the admin panel
5. create a minimal experiment
6. verify static assets load correctly
7. verify packaged runtime directories are writable

## Versioning

Packaging is tied to the top-level version file:

- `/Users/rossetti/PycharmProjects/YWeb/VERSION`

Update it before release builds.
