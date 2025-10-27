"""
Test for new optional client form fields: network structure and hourly activity rates.
"""

from unittest.mock import Mock, patch

import pytest


class TestClientFormFields:
    """Test client form optional fields"""

    def test_clients_routes_has_create_client(self):
        """Test that create_client route exists"""
        try:
            from y_web.routes_admin import clients_routes

            assert clients_routes is not None
            assert hasattr(clients_routes, "create_client")

        except ImportError as e:
            pytest.skip(f"Could not import clients_routes: {e}")

    def test_network_model_field_handling(self):
        """Test that network model field can be extracted from form"""
        try:
            from flask import Flask
            from werkzeug.datastructures import ImmutableMultiDict

            app = Flask(__name__)
            with app.test_request_context(
                method="POST",
                data={
                    "network_model": "BA",
                    "network_m": "2",
                    "network_p": "0.1",
                },
            ):
                from flask import request

                network_model = request.form.get("network_model")
                network_m = request.form.get("network_m")
                network_p = request.form.get("network_p")

                assert network_model == "BA"
                assert network_m == "2"
                assert network_p == "0.1"

        except ImportError as e:
            pytest.skip(f"Could not import Flask: {e}")

    def test_hourly_activity_field_handling(self):
        """Test that hourly activity fields can be extracted from form"""
        try:
            from flask import Flask

            app = Flask(__name__)

            # Prepare form data for all 24 hours
            form_data = {}
            for hour in range(24):
                form_data[f"hourly_{hour}"] = "0.042"

            with app.test_request_context(method="POST", data=form_data):
                from flask import request

                # Test extraction
                hourly_activity_custom = {}
                for hour in range(24):
                    hourly_val = request.form.get(f"hourly_{hour}")
                    if hourly_val and hourly_val.strip():
                        try:
                            hourly_activity_custom[str(hour)] = float(hourly_val)
                        except ValueError:
                            pass

                # Verify all 24 hours were extracted
                assert len(hourly_activity_custom) == 24
                assert hourly_activity_custom["0"] == 0.042
                assert hourly_activity_custom["23"] == 0.042

        except ImportError as e:
            pytest.skip(f"Could not import Flask: {e}")

    def test_network_file_field_handling(self):
        """Test that network file can be extracted from form"""
        try:
            from io import BytesIO

            from flask import Flask
            from werkzeug.datastructures import FileStorage

            app = Flask(__name__)

            # Create a mock file
            file_data = b"agent1,agent2\nagent2,agent3\n"
            file = FileStorage(
                stream=BytesIO(file_data),
                filename="network.csv",
                content_type="text/csv",
            )

            with app.test_request_context(method="POST", data={"network_file": file}):
                from flask import request

                network_file = request.files.get("network_file")
                assert network_file is not None
                assert network_file.filename == "network.csv"

        except ImportError as e:
            pytest.skip(f"Could not import Flask: {e}")

    def test_optional_fields_can_be_empty(self):
        """Test that optional fields can be left empty without errors"""
        try:
            from flask import Flask

            app = Flask(__name__)

            # Test with empty optional fields
            form_data = {
                "name": "test_client",
                "descr": "Test description",
                "network_model": "",
                "hourly_0": "",
            }

            with app.test_request_context(method="POST", data=form_data):
                from flask import request

                network_model = request.form.get("network_model")
                hourly_0 = request.form.get("hourly_0")

                # Both should be empty strings or None
                assert network_model == ""
                assert hourly_0 == ""

                # Test hourly activity logic
                hourly_activity_custom = {}
                for hour in range(24):
                    hourly_val = request.form.get(f"hourly_{hour}")
                    if hourly_val and hourly_val.strip():
                        try:
                            hourly_activity_custom[str(hour)] = float(hourly_val)
                        except ValueError:
                            pass

                # Should be empty since no valid values provided
                assert len(hourly_activity_custom) == 0

        except ImportError as e:
            pytest.skip(f"Could not import Flask: {e}")

    def test_recsys_field_handling(self):
        """Test that recsys fields can be extracted from form"""
        try:
            from flask import Flask

            app = Flask(__name__)

            # Test with recsys fields
            form_data = {
                "name": "test_client",
                "descr": "Test description",
                "recsys_type": "default",
                "frecsys_type": "random",
            }

            with app.test_request_context(method="POST", data=form_data):
                from flask import request

                recsys_type = request.form.get("recsys_type")
                frecsys_type = request.form.get("frecsys_type")

                # Both should have the specified values
                assert recsys_type == "default"
                assert frecsys_type == "random"

        except ImportError as e:
            pytest.skip(f"Could not import Flask: {e}")

