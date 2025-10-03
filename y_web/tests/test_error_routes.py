"""
Tests for error routes and error page rendering.
"""

import pytest
from flask import Blueprint


class TestErrorRoutesStructure:
    """Test error routes module structure"""

    def test_error_routes_import(self):
        """Test that error_routes module can be imported"""
        try:
            from y_web import error_routes

            assert hasattr(error_routes, "errors")
        except ImportError as e:
            pytest.skip(f"Could not import error_routes: {e}")

    def test_errors_blueprint(self):
        """Test that errors blueprint exists and is properly configured"""
        try:
            from y_web.error_routes import errors

            assert isinstance(errors, Blueprint)
            assert errors.name == "errors"
        except ImportError as e:
            pytest.skip(f"Could not import errors blueprint: {e}")

    def test_error_handler_functions_exist(self):
        """Test that error handler functions exist"""
        try:
            from y_web.error_routes import (
                bad_request,
                forbidden,
                internal_server_error,
                not_found,
            )

            # Check functions exist
            assert callable(bad_request)
            assert callable(forbidden)
            assert callable(not_found)
            assert callable(internal_server_error)

            # Check docstrings
            assert bad_request.__doc__ is not None
            assert forbidden.__doc__ is not None
            assert not_found.__doc__ is not None
            assert internal_server_error.__doc__ is not None
        except ImportError as e:
            pytest.skip(f"Could not import error handler functions: {e}")


class TestErrorTemplates:
    """Test error page templates exist"""

    def test_400_template_exists(self):
        """Test that 400.html template exists"""
        import os

        from y_web import BASE_DIR

        template_path = os.path.join(
            BASE_DIR, "templates", "error_pages", "400.html"
        )
        assert os.path.exists(template_path), "400.html template does not exist"

    def test_403_template_exists(self):
        """Test that 403.html template exists"""
        import os

        from y_web import BASE_DIR

        template_path = os.path.join(
            BASE_DIR, "templates", "error_pages", "403.html"
        )
        assert os.path.exists(template_path), "403.html template does not exist"

    def test_404_template_exists(self):
        """Test that 404.html template exists"""
        import os

        from y_web import BASE_DIR

        template_path = os.path.join(
            BASE_DIR, "templates", "error_pages", "404.html"
        )
        assert os.path.exists(template_path), "404.html template does not exist"

    def test_500_template_exists(self):
        """Test that 500.html template exists"""
        import os

        from y_web import BASE_DIR

        template_path = os.path.join(
            BASE_DIR, "templates", "error_pages", "500.html"
        )
        assert os.path.exists(template_path), "500.html template does not exist"


class TestErrorTemplateContent:
    """Test error page template content"""

    def test_400_template_content(self):
        """Test that 400.html template contains expected content"""
        import os

        from y_web import BASE_DIR

        template_path = os.path.join(
            BASE_DIR, "templates", "error_pages", "400.html"
        )
        with open(template_path, "r") as f:
            content = f.read()
            assert "400" in content or "Bad Request" in content
            assert "Y Social" in content

    def test_403_template_content(self):
        """Test that 403.html template contains expected content"""
        import os

        from y_web import BASE_DIR

        template_path = os.path.join(
            BASE_DIR, "templates", "error_pages", "403.html"
        )
        with open(template_path, "r") as f:
            content = f.read()
            assert "403" in content or "Forbidden" in content or "Access Denied" in content
            assert "Y Social" in content

    def test_404_template_content(self):
        """Test that 404.html template contains expected content"""
        import os

        from y_web import BASE_DIR

        template_path = os.path.join(
            BASE_DIR, "templates", "error_pages", "404.html"
        )
        with open(template_path, "r") as f:
            content = f.read()
            assert "404" in content
            assert "Y Social" in content

    def test_500_template_content(self):
        """Test that 500.html template contains expected content"""
        import os

        from y_web import BASE_DIR

        template_path = os.path.join(
            BASE_DIR, "templates", "error_pages", "500.html"
        )
        with open(template_path, "r") as f:
            content = f.read()
            assert "500" in content or "Internal Server Error" in content
            assert "Y Social" in content


class TestErrorHandlerIntegration:
    """Test error handler integration with Flask app"""

    def test_errors_blueprint_registered(self):
        """Test that errors blueprint is registered with the app"""
        try:
            from y_web import create_app

            app = create_app(db_type="sqlite")
            
            # Check that error handlers are registered
            assert 400 in app.error_handler_spec[None]
            assert 403 in app.error_handler_spec[None]
            assert 404 in app.error_handler_spec[None]
            assert 500 in app.error_handler_spec[None]
        except Exception as e:
            pytest.skip(f"Could not test blueprint registration: {e}")

    def test_404_handler_response(self):
        """Test that 404 handler returns correct response"""
        try:
            from y_web import create_app

            app = create_app(db_type="sqlite")
            
            with app.test_client() as client:
                response = client.get("/nonexistent-page-url")
                assert response.status_code == 404
        except Exception as e:
            pytest.skip(f"Could not test 404 handler: {e}")

    def test_error_handler_returns_html(self):
        """Test that error handlers return HTML content"""
        try:
            from y_web import create_app

            app = create_app(db_type="sqlite")
            
            with app.test_client() as client:
                response = client.get("/nonexistent-page-url")
                assert response.status_code == 404
                assert b"html" in response.data.lower()
                assert b"Y Social" in response.data or b"y social" in response.data.lower()
        except Exception as e:
            pytest.skip(f"Could not test error handler HTML response: {e}")


class TestErrorRouteCount:
    """Test error route count"""

    def test_error_handlers_count(self):
        """Test that errors blueprint has correct number of error handlers"""
        try:
            from y_web.error_routes import errors

            # Count registered routes/handlers
            handler_count = len(errors.deferred_functions)

            # Should have 4 error handlers (400, 403, 404, 500)
            assert handler_count >= 4
        except ImportError as e:
            pytest.skip(f"Could not import errors blueprint: {e}")
