# Contributing to YSocial

Thank you for your interest in contributing to YSocial! This document provides guidelines and workflows for contributing to the project.

## Development Workflow

### Prerequisites

- Python 3.10 or higher
- Git

### Setting Up Development Environment

1. Clone the repository with submodules:
```bash
git clone --recurse-submodules https://github.com/YSocialTwin/YSocial.git
cd YSocial
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Install development tools:
```bash
pip install black isort pytest
```

## Code Quality Standards

YSocial uses automated tools to maintain code quality and consistency.

### Code Formatting

We use **Black** for code formatting and **isort** for import sorting. These tools are automatically run via GitHub Actions when you push code.

#### Running Locally (Recommended)

Before committing, format your code locally:

```bash
# Sort imports
isort .

# Format code
black .
```

Or run both at once:
```bash
isort . && black .
```

#### Checking Without Modifying

To check if your code needs formatting:

```bash
# Check import sorting
isort --check-only .

# Check code formatting
black --check .
```

### Configuration

Formatting tools are configured in `pyproject.toml`:
- Line length: 88 characters (Black default)
- Import style: Black-compatible
- External dependencies excluded from formatting

## Testing

### Running Tests

Run the full test suite:

```bash
python run_tests.py
```

Or use pytest directly:

```bash
# Run all tests
pytest y_web/tests/ -v

# Run specific test file
pytest y_web/tests/test_simple_models.py -v

# Run with coverage
pytest y_web/tests/ --cov=y_web --cov-report=html
```

### Writing Tests

- Place tests in `y_web/tests/`
- Follow the naming convention `test_*.py`
- Use descriptive test names
- Keep tests isolated and independent
- See `y_web/tests/README.md` for more details

## GitHub Actions Workflows

YSocial includes automated workflows that run on every push and pull request:

### 1. CI - Run Tests

**Workflow:** `.github/workflows/ci-tests.yml`

Automatically runs the test suite on every push and pull request to `main` and `develop` branches.

- Installs all dependencies
- Runs `python run_tests.py`
- Reports test results

### 2. Format Code

**Workflow:** `.github/workflows/format-code.yml`

Automatically formats code when Python files are modified:

**For pushes to `main`/`develop`:**
- Runs `isort` to sort imports
- Runs `black` to format code
- Automatically commits and pushes formatting changes (if any)
- Uses `[skip ci]` to prevent recursive triggers

**For pull requests:**
- Checks if code is properly formatted
- Fails the check if formatting is needed
- Requires you to format code locally and push again

### Best Practices

1. **Format code locally before pushing** to avoid automatic commits
2. **Run tests locally** to catch issues early
3. **Check the Actions tab** on GitHub to see workflow results
4. **Use meaningful commit messages** following conventional commits

## Pull Request Process

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/your-feature-name`
3. Make your changes
4. Format your code: `isort . && black .`
5. Run tests: `python run_tests.py`
6. Commit your changes: `git commit -m "Add feature: description"`
7. Push to your fork: `git push origin feature/your-feature-name`
8. Create a Pull Request

### Pull Request Checklist

- [ ] Code is properly formatted (isort + black)
- [ ] All tests pass
- [ ] New tests added for new functionality
- [ ] Documentation updated (if applicable)
- [ ] Commit messages are clear and descriptive

## Code Review

All pull requests require review before merging. Reviewers will check:

- Code quality and style
- Test coverage
- Documentation
- Performance implications
- Security considerations

## Getting Help

- **Issues:** Use GitHub Issues for bug reports and feature requests
- **Discussions:** Use GitHub Discussions for questions and general discussion
- **Website:** Visit [https://ysocialtwin.github.io/](https://ysocialtwin.github.io/)

## License

By contributing to YSocial, you agree that your contributions will be licensed under the project's license.

## Questions?

Feel free to open an issue or start a discussion if you have any questions about contributing!
