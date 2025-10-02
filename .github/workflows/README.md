# GitHub Actions Workflows

This directory contains automated workflows for the YSocial project.

## Workflows

### 1. CI - Run Tests (`ci-tests.yml`)

**Trigger:** Push or pull request to `main` or `develop` branches

This workflow:
- Checks out the code with submodules
- Sets up Python 3.10
- Caches pip dependencies for faster builds
- Installs all project dependencies from `requirements.txt`
- Runs the test suite using `run_tests.py`

**Entry Point:** `python run_tests.py`

The test runner executes all pytest tests defined in the `y_web/tests/` directory.

### 2. Format Code (`format-code.yml`)

**Trigger:** Push or pull request to `main` or `develop` branches (only when `.py` files change)

This workflow:
- Checks out the code
- Sets up Python 3.10
- Installs `black` and `isort` formatters
- Sorts imports using `isort` (configured via `pyproject.toml`)
- Formats code using `black` (configured via `pyproject.toml`)
- For pushes to `main`/`develop`: Automatically commits and pushes formatting changes
- For pull requests: Fails the check if code is not properly formatted (requires local formatting)

**Configuration Files:**
- `pyproject.toml` - Contains settings for both `black` and `isort`
- `.isort.cfg` - Additional `isort` configuration

## Running Locally

### Run Tests
```bash
python run_tests.py
```

### Format Code
```bash
# Sort imports
isort .

# Format with black
black .

# Or run both
isort . && black .
```

### Check Formatting (without modifying files)
```bash
# Check if imports are sorted
isort --check-only .

# Check if code is formatted
black --check .
```

## Notes

- The format workflow uses `[skip ci]` in commit messages to prevent triggering itself recursively
- The CI test workflow runs on all pushes and pull requests to ensure code quality
- Both workflows use caching to speed up dependency installation
