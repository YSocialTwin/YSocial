# Y_Web Test Suite

This directory contains the pytest test suite for the y_web Flask application.

## Overview

The test suite is designed to test various components of the y_web application including:

- Database models and relationships
- Authentication and authorization
- Flask application structure and configuration  
- Utility functions
- Blueprint registration and routing

## Test Structure

### Working Test Files

- `test_simple_models.py` - Tests for database models with SQLAlchemy
- `test_simple_auth.py` - Tests for authentication functionality with Flask-Login
- `test_app_structure.py` - Tests for Flask application structure and configuration
- `test_utils.py` - Tests for utility functions (many skipped due to optional dependencies)

### Configuration Files

- `conftest.py` - Pytest fixtures and configuration
- `__init__.py` - Makes the tests directory a Python package

## Running Tests

### Using the Test Runner

```bash
python run_tests.py
```

### Using pytest directly

```bash
# Run all working tests
pytest y_web/tests/test_simple_models.py y_web/tests/test_simple_auth.py y_web/tests/test_app_structure.py y_web/tests/test_utils.py -v

# Run specific test file
pytest y_web/tests/test_simple_models.py -v

# Run specific test
pytest y_web/tests/test_simple_models.py::test_user_model_creation -v
```

### Running with coverage

```bash
pytest y_web/tests/ --cov=y_web --cov-report=html
```

## Test Categories

### Unit Tests
- Model creation and validation
- Password hashing and security
- Basic Flask functionality
- Database operations

### Integration Tests  
- Authentication workflow
- Blueprint registration
- Database relationships
- Flask-Login integration

## Dependencies

### Required
- pytest
- pytest-flask
- Flask
- Flask-SQLAlchemy
- Flask-Login
- Werkzeug

### Optional (for skipped tests)
- feedparser
- nltk
- perspective
- ollama
- Various other y_web specific dependencies

## Test Design Principles

1. **Isolation** - Each test uses its own temporary database
2. **Minimal Dependencies** - Tests avoid importing the full y_web application when possible
3. **Fast Execution** - Tests complete quickly for rapid feedback
4. **Clear Assertions** - Tests have explicit assertions that are easy to understand
5. **Cleanup** - All tests clean up temporary resources

## Current Test Results

As of the latest run:
- ✅ 26 tests passed
- ⏭️ 11 tests skipped (due to missing optional dependencies)
- ❌ 0 tests failed

## Adding New Tests

When adding new tests:

1. Follow the naming convention `test_*.py`
2. Use descriptive test names that explain what is being tested
3. Keep tests isolated and independent
4. Clean up any resources (databases, files, etc.)
5. Use appropriate pytest fixtures from `conftest.py`
6. Add docstrings to explain complex test scenarios

## Known Issues

- Some tests are skipped due to optional dependencies not being installed
- The original complex models with database binds are not yet fully testable
- Full application integration tests require more dependency management

## Future Improvements

- Add more comprehensive integration tests
- Add API endpoint testing
- Add template rendering tests
- Improve dependency management for optional features
- Add performance tests
- Add security testing