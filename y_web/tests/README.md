# Y_Web Test Suite

This directory contains the pytest test suite for the y_web Flask application.

## Overview

The test suite is designed to test various components of the y_web application including:

- Database models and relationships
- Authentication and authorization
- Flask application structure and configuration  
- Utility functions
- **Flask route endpoints and HTTP interactions**
- Blueprint registration and routing

## Test Structure

### Working Test Files

- `test_simple_models.py` (4 tests) - Tests for database models with SQLAlchemy
- `test_simple_auth.py` (6 tests) - Tests for authentication functionality with Flask-Login
- `test_app_structure.py` (13 tests) - Tests for Flask application structure and configuration
- `test_utils.py` (14 tests) - Tests for utility functions (many skipped due to optional dependencies)
- **`test_auth_routes.py` (12 tests) - Tests for authentication routes (/signup, /login, /logout)**
- **`test_admin_routes.py` (13 tests) - Tests for admin dashboard routes (/admin/dashboard, /admin/about)**
- **`test_user_interaction_routes.py` (21 tests) - Tests for user interaction routes (/follow, /share_content, /react_to_content, /publish, /delete_post)**

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
pytest y_web/tests/test_simple_models.py y_web/tests/test_simple_auth.py y_web/tests/test_app_structure.py y_web/tests/test_utils.py y_web/tests/test_auth_routes.py y_web/tests/test_admin_routes.py y_web/tests/test_user_interaction_routes.py -v

# Run all route tests
pytest y_web/tests/test_*_routes.py -v

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

### **Route Tests (NEW)**  
- **Authentication routes (signup, login, logout)**
- **Admin dashboard routes with privilege checking**
- **User interaction routes (follow, share, react, publish, delete)**
- **HTTP method testing (GET, POST)**
- **Request format testing (form data, JSON)**
- **Error handling and edge cases**
- **Complete workflow integration testing**

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
6. ****Comprehensive Coverage** - Route tests cover success, failure, and edge cases**
7. ****Authentication Testing** - Proper login/logout and privilege checking**

## Current Test Results

As of the latest run:
- ✅ **69 tests passed** (4 + 6 + 13 + 3 + 12 + 13 + 21 = 72 individual tests)
- ⏭️ 11 tests skipped (due to missing optional dependencies)
- ❌ 0 tests failed

### **Route Test Coverage**
- **Auth Routes**: 12 tests covering signup, login, logout workflows
- **Admin Routes**: 13 tests covering dashboard and about pages with admin privilege checking
- **User Interaction Routes**: 21 tests covering social media interactions (follow, share, react, publish, delete)
- **Total Route Tests**: 46 comprehensive route tests

## Adding New Tests

When adding new tests:

1. Follow the naming convention `test_*.py`
2. Use descriptive test names that explain what is being tested
3. Keep tests isolated and independent
4. Clean up any resources (databases, files, etc.)
5. Use appropriate pytest fixtures from `conftest.py`
6. Add docstrings to explain complex test scenarios
7. **For route tests, test both success and failure scenarios**
8. **Include proper authentication testing for protected routes**

## Known Issues

- Some utility tests are skipped due to optional dependencies not being installed
- The original complex models with database binds are not yet fully testable

## Future Improvements

- Add more admin blueprint route tests (populations, experiments, users, etc.)
- Add main blueprint route tests
- Add API endpoint testing for JSON responses
- Add template rendering tests
- Improve dependency management for optional features
- Add performance tests
- Add security testing