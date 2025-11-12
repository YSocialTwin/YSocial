"""
Tests for macOS code signing configuration.

This test module validates that the PyInstaller spec file is properly
configured with entitlements for macOS distribution.
"""

import os
import xml.etree.ElementTree as ET
from pathlib import Path


def test_entitlements_file_exists():
    """Test that entitlements.plist file exists in the packaging directory."""
    project_root = Path(__file__).parent.parent.parent
    entitlements_path = project_root / "packaging" / "entitlements.plist"
    assert (
        entitlements_path.exists()
    ), "entitlements.plist file not found in packaging directory"


def test_entitlements_file_valid_xml():
    """Test that entitlements.plist is valid XML."""
    project_root = Path(__file__).parent.parent.parent
    entitlements_path = project_root / "packaging" / "entitlements.plist"

    try:
        tree = ET.parse(entitlements_path)
        root = tree.getroot()
        assert root.tag == "plist", "Root element should be 'plist'"
    except ET.ParseError as e:
        assert False, f"entitlements.plist is not valid XML: {e}"


def test_entitlements_contains_required_keys():
    """Test that entitlements.plist contains all required security keys."""
    project_root = Path(__file__).parent.parent.parent
    entitlements_path = project_root / "packaging" / "entitlements.plist"

    tree = ET.parse(entitlements_path)
    root = tree.getroot()

    # Find the dict element
    dict_elem = root.find("dict")
    assert dict_elem is not None, "dict element not found in plist"

    # Extract all keys
    keys = [key.text for key in dict_elem.findall("key")]

    # Required entitlements for PyInstaller one-file executables
    required_keys = [
        "com.apple.security.cs.allow-unsigned-executable-memory",
        "com.apple.security.cs.allow-dyld-environment-variables",
        "com.apple.security.cs.disable-library-validation",
        "com.apple.security.cs.allow-jit",
    ]

    for required_key in required_keys:
        assert (
            required_key in keys
        ), f"Required entitlement '{required_key}' not found in entitlements.plist"


def test_spec_file_references_entitlements():
    """Test that y_social.spec references the entitlements file."""
    project_root = Path(__file__).parent.parent.parent
    spec_path = project_root / "y_social.spec"

    with open(spec_path, "r") as f:
        spec_content = f.read()

    assert (
        "entitlements.plist" in spec_content
    ), "y_social.spec does not reference entitlements.plist"
    assert (
        'entitlements_file=os.path.join(basedir, "packaging", "entitlements.plist")'
        in spec_content
    ), "entitlements_file not properly configured in spec (should be in packaging directory)"


def test_spec_file_is_onefile_mode():
    """Test that y_social.spec is configured for one-file mode."""
    project_root = Path(__file__).parent.parent
    spec_path = project_root / "y_social.spec"

    with open(spec_path, "r") as f:
        spec_content = f.read()

    # In one-file mode, EXE should contain a.binaries, a.zipfiles, and a.datas
    # Search for the EXE section
    import re

    exe_match = re.search(r"exe = EXE\((.*?)\)", spec_content, re.DOTALL)
    assert exe_match, "Could not find EXE section in spec file"

    exe_content = exe_match.group(1)

    # Check for one-file mode indicators
    assert "a.binaries" in exe_content, "a.binaries not in EXE (not one-file mode)"
    assert "a.zipfiles" in exe_content, "a.zipfiles not in EXE (not one-file mode)"
    assert "a.datas" in exe_content, "a.datas not in EXE (not one-file mode)"

    # One-file mode should NOT have a COLLECT statement
    assert "COLLECT" not in spec_content, "COLLECT found - this indicates onedir mode"


def test_macos_code_signing_documentation_exists():
    """Test that macOS code signing documentation exists."""
    project_root = Path(__file__).parent.parent
    doc_path = project_root / "MACOS_CODE_SIGNING.md"
    assert doc_path.exists(), "MACOS_CODE_SIGNING.md documentation not found"


def test_macos_code_signing_documentation_content():
    """Test that code signing documentation contains key information."""
    project_root = Path(__file__).parent.parent
    doc_path = project_root / "MACOS_CODE_SIGNING.md"

    with open(doc_path, "r") as f:
        doc_content = f.read()

    # Check for key sections and commands
    assert "codesign" in doc_content, "codesign command not mentioned"
    assert "entitlements.plist" in doc_content, "entitlements.plist not mentioned"
    assert (
        "com.apple.security.cs.disable-library-validation" in doc_content
    ), "Key entitlement not explained"
    assert "--options runtime" in doc_content, "Hardened Runtime option not mentioned"
    assert (
        "one-file" in doc_content.lower()
    ), "One-file mode not mentioned in documentation"


def test_build_documentation_mentions_signing():
    """Test that BUILD_EXECUTABLES.md mentions code signing for macOS."""
    project_root = Path(__file__).parent.parent
    doc_path = project_root / "packaging" / "BUILD_EXECUTABLES.md"

    with open(doc_path, "r") as f:
        doc_content = f.read()

    # Check for macOS signing mentions
    assert "codesign" in doc_content, "codesign not mentioned in build docs"
    assert (
        "MACOS_CODE_SIGNING.md" in doc_content
    ), "Reference to MACOS_CODE_SIGNING.md not found"


def test_github_workflow_has_macos_signing_step():
    """Test that GitHub Actions workflow includes macOS signing."""
    project_root = Path(__file__).parent.parent
    workflow_path = project_root / ".github" / "workflows" / "build-executables.yml"

    with open(workflow_path, "r") as f:
        workflow_content = f.read()

    # Check for macOS signing step
    assert (
        "Sign macOS executable" in workflow_content
    ), "macOS signing step not found in workflow"
    assert (
        "runner.os == 'macOS'" in workflow_content
    ), "macOS conditional check not found"
    assert (
        "codesign --force --sign -" in workflow_content
    ), "codesign command not found in workflow"
    assert (
        "entitlements.plist" in workflow_content
    ), "entitlements.plist not used in workflow"
