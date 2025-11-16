#!/usr/bin/env python3
"""
Validation script for multi-file PyInstaller packaging migration.

This script validates that the changes made for multi-file packaging
are correct and will work as expected.
"""

import os
import sys
from pathlib import Path


def validate_spec_file():
    """Validate that y_social.spec has COLLECT step for multi-file packaging."""
    print("Checking y_social.spec for multi-file packaging...")
    
    spec_path = Path(__file__).parent / "y_social.spec"
    if not spec_path.exists():
        print("  ❌ y_social.spec not found")
        return False
    
    content = spec_path.read_text()
    
    # Check for COLLECT step
    if "coll = COLLECT(" not in content:
        print("  ❌ COLLECT step not found in y_social.spec")
        return False
    
    # Check that binaries/datas are NOT in EXE (single-file mode)
    # Look for the EXE definition and ensure it doesn't have a.binaries, a.datas, etc. after a.scripts
    exe_section = content[content.find("exe = EXE("):content.find("coll = COLLECT(")]
    
    # The correct pattern should be: exe = EXE(pyz, a.scripts, [], ...) for multi-file
    # or minimal content between a.scripts and name= for multi-file
    if "a.binaries," in exe_section and "a.zipfiles," in exe_section and "a.datas," in exe_section:
        print("  ❌ EXE still includes a.binaries, a.zipfiles, a.datas (single-file mode)")
        return False
    
    print("  ✅ y_social.spec correctly configured for multi-file packaging")
    return True


def validate_path_utils():
    """Validate that path_utils.py comments reflect multi-file mode."""
    print("Checking y_web/utils/path_utils.py for multi-file documentation...")
    
    path_utils = Path(__file__).parent / "y_web" / "utils" / "path_utils.py"
    if not path_utils.exists():
        print("  ❌ path_utils.py not found")
        return False
    
    content = path_utils.read_text()
    
    # Check for multi-file mode documentation
    if "multi-file mode" not in content.lower() and "onedir" not in content.lower():
        print("  ⚠️  path_utils.py doesn't mention multi-file mode (but may still work)")
        return True
    
    print("  ✅ path_utils.py has multi-file mode documentation")
    return True


def validate_macos_scripts():
    """Validate that macOS packaging scripts handle directories."""
    print("Checking macOS packaging scripts for directory handling...")
    
    build_script = Path(__file__).parent / "packaging" / "build_and_package_macos.sh"
    dmg_script = Path(__file__).parent / "packaging" / "create_dmg.sh"
    
    if not build_script.exists():
        print("  ❌ build_and_package_macos.sh not found")
        return False
    
    if not dmg_script.exists():
        print("  ❌ create_dmg.sh not found")
        return False
    
    build_content = build_script.read_text()
    dmg_content = dmg_script.read_text()
    
    # Check build script looks for directory
    if 'if [ ! -d "dist/YSocial" ]' not in build_content:
        print("  ❌ build_and_package_macos.sh doesn't check for dist/YSocial directory")
        return False
    
    # Check build script signs libraries
    if "find dist/YSocial" not in build_content or ".dylib" not in build_content:
        print("  ❌ build_and_package_macos.sh doesn't sign .dylib files")
        return False
    
    # Check DMG script handles directory
    if 'SOURCE_APP_DIR="dist/${APP_NAME}"' not in dmg_content:
        print("  ❌ create_dmg.sh doesn't define SOURCE_APP_DIR for directory")
        return False
    
    if "cp -R" not in dmg_content:
        print("  ❌ create_dmg.sh doesn't copy directory recursively")
        return False
    
    print("  ✅ macOS scripts correctly handle multi-file directory")
    return True


def validate_documentation():
    """Validate that documentation mentions multi-file packaging."""
    print("Checking documentation for multi-file updates...")
    
    build_doc = Path(__file__).parent / "packaging" / "BUILD_EXECUTABLES.md"
    migration_doc = Path(__file__).parent / "packaging" / "MULTIFILE_MIGRATION.md"
    
    if not build_doc.exists():
        print("  ❌ BUILD_EXECUTABLES.md not found")
        return False
    
    build_content = build_doc.read_text()
    
    # Check BUILD_EXECUTABLES.md mentions multi-file
    if "multi-file" not in build_content.lower() and "onedir" not in build_content.lower():
        print("  ❌ BUILD_EXECUTABLES.md not updated for multi-file packaging")
        return False
    
    # Check for directory in output path
    if "dist/YSocial/" not in build_content:
        print("  ⚠️  BUILD_EXECUTABLES.md doesn't show dist/YSocial/ directory")
    
    # Check for migration documentation
    if not migration_doc.exists():
        print("  ⚠️  MULTIFILE_MIGRATION.md not found (recommended but optional)")
    else:
        print("  ✅ MULTIFILE_MIGRATION.md exists")
    
    print("  ✅ Documentation updated for multi-file packaging")
    return True


def check_gitignore():
    """Check that .gitignore properly handles dist directory."""
    print("Checking .gitignore for dist directory...")
    
    gitignore = Path(__file__).parent / ".gitignore"
    if not gitignore.exists():
        print("  ⚠️  .gitignore not found")
        return True
    
    content = gitignore.read_text()
    
    if "dist/" not in content and "dist" not in content:
        print("  ⚠️  .gitignore doesn't exclude dist/ (will commit build artifacts)")
        return True
    
    print("  ✅ .gitignore properly excludes dist/")
    return True


def main():
    """Run all validation checks."""
    print("=" * 60)
    print("Multi-File PyInstaller Packaging Validation")
    print("=" * 60)
    print()
    
    results = []
    
    results.append(("y_social.spec", validate_spec_file()))
    print()
    results.append(("path_utils.py", validate_path_utils()))
    print()
    results.append(("macOS scripts", validate_macos_scripts()))
    print()
    results.append(("Documentation", validate_documentation()))
    print()
    results.append((".gitignore", check_gitignore()))
    print()
    
    print("=" * 60)
    print("VALIDATION SUMMARY")
    print("=" * 60)
    
    all_passed = True
    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}: {name}")
        if not result:
            all_passed = False
    
    print()
    
    if all_passed:
        print("✅ All validation checks passed!")
        print()
        print("Next steps:")
        print("1. Install PyInstaller: pip install pyinstaller")
        print("2. Build the executable: pyinstaller y_social.spec --clean --noconfirm")
        print("3. Verify output is a directory: ls -la dist/YSocial/")
        print("4. Test startup time improvement")
        print("5. Run full test suite if available")
        return 0
    else:
        print("❌ Some validation checks failed!")
        print("Please review the errors above and fix the issues.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
