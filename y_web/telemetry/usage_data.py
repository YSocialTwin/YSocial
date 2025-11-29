import json
import os
import re
import shutil
import sys
import tempfile
import traceback
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import requests

from y_web.pyinstaller_utils import installation_id

# Support contact email for telemetry issues
SUPPORT_EMAIL = "support@y-not.social"


class Telemetry(object):
    # telemetry.y-not.social
    def __init__(self, host="telemetry.y-not.social", port=9000, user=None):
        self.host = host
        self.port = port
        self.uuid = None
        self.user = user
        self.enabled = self._check_telemetry_enabled()

        config_dir = installation_id.get_installation_config_dir()

        id_file = config_dir / "installation_id.json"

        if id_file.exists():
            try:
                with open(id_file, "r") as f:
                    installation_info = json.load(f)
                    self.uuid = installation_info.get("installation_id", None)
            except Exception:
                pass
        else:
            self.uuid = None

    def _check_telemetry_enabled(self):
        """
        Check if telemetry is enabled for the current user.

        Returns:
            bool: True if telemetry is enabled, False otherwise
        """
        if self.user is None:
            return True  # Default to enabled if no user context

        # Check if user is authenticated
        if not hasattr(self.user, "is_authenticated") or not self.user.is_authenticated:
            return True  # Default to enabled for anonymous users

        # Check if user has telemetry_enabled attribute (Admin_users)
        if hasattr(self.user, "telemetry_enabled"):
            return bool(self.user.telemetry_enabled)

        return True  # Default to enabled if attribute doesn't exist

    def register_update_app(self, data, action="register"):
        """
        Register or update app installation on telemetry server using endpoints
        :param data:
        :param action:
        :return:
        """
        if not self.enabled:
            return False

        try:
            config_dir = installation_id.get_installation_config_dir()
            id_file = config_dir / "installation_id.json"
            with open(id_file, "r") as f:
                data = json.load(f)
                data["uiid"] = self.uuid
                if action == "register":
                    data["action"] = "register"
                    response = requests.post(
                        f"http://{self.host}:{self.port}/api/register", json=data
                    )
                elif action == "update":
                    data["action"] = "update"
                    response = requests.post(
                        f"http://{self.host}:{self.port}/api/register", json=data
                    )
                    return True
        except:
            return False

    def log_event(self, data):
        """
        Log event data to telemetry server using endpoints
        :param data:
        :return:
        """
        if not self.enabled:
            return False

        data["uiid"] = self.uuid
        data["timestamp"] = (
            datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        )

        if "data" not in data:
            data["data"] = {}

        try:
            response = requests.post(
                f"http://{self.host}:{self.port}/api/log_event", json=data
            )
            return True
        except:
            return False

    def log_stack_trace(self, data):
        """
        Log stack trace data to telemetry server using endpoints
        :param data:
        :return:
        """
        if not self.enabled:
            return False

        stacktrace = data["stacktrace"]
        safe_trace = self.__anonymize_traceback(stacktrace)
        data["stacktrace"] = safe_trace
        data["uiid"] = self.uuid
        data["timestamp"] = (
            datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        )

        try:
            response = requests.post(
                f"http://{self.host}:{self.port}/api/log_stack_trace", json=data
            )
            return True
        except:
            return False

    def submit_experiment_logs(
        self, experiment_id, experiment_folder_path, problem_description=None
    ):
        """
        Compress and send experiment log files and configuration to telemetry server.

        :param experiment_id: ID of the experiment
        :param experiment_folder_path: Path to the experiment folder containing logs and configs
        :param problem_description: Optional description of the problem from the user
        :return: tuple (success: bool, message: str)
        """
        if not self.enabled:
            return (
                False,
                "Telemetry is disabled. Please enable it in your user settings.",
            )

        temp_zip_path = None
        temp_dir = None
        try:
            experiment_path = Path(experiment_folder_path)

            if not experiment_path.exists():
                return False, f"Experiment folder not found: {experiment_folder_path}"

            # Create a temporary directory for processing files
            temp_dir = tempfile.mkdtemp()
            temp_dir_path = Path(temp_dir)

            # Create a temporary zip file
            with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as temp_zip:
                temp_zip_path = temp_zip.name

            # Compress log files and JSON configuration files
            with zipfile.ZipFile(temp_zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
                files_added = 0
                for file_path in experiment_path.rglob("*"):
                    if file_path.is_file():
                        # Include .log files and .json configuration files
                        if file_path.suffix.lower() in [".log", ".json"]:
                            arcname = file_path.relative_to(experiment_path)

                            if file_path.suffix.lower() == ".log":
                                # For log files, include only last 300 rows and anonymize paths
                                temp_log_path = temp_dir_path / arcname
                                temp_log_path.parent.mkdir(parents=True, exist_ok=True)

                                try:
                                    with open(
                                        file_path,
                                        "r",
                                        encoding="utf-8",
                                        errors="ignore",
                                    ) as f:
                                        lines = f.readlines()

                                    # Get last 300 lines
                                    last_lines = (
                                        lines[-300:] if len(lines) > 300 else lines
                                    )

                                    # Anonymize each line
                                    anonymized_lines = [
                                        self._anonymize_log_line(line)
                                        for line in last_lines
                                    ]

                                    with open(
                                        temp_log_path, "w", encoding="utf-8"
                                    ) as f:
                                        f.writelines(anonymized_lines)

                                    zipf.write(temp_log_path, arcname)
                                    files_added += 1
                                except Exception as e:
                                    # If we can't read the log file, skip it
                                    continue

                            elif file_path.suffix.lower() == ".json":
                                # For JSON files, sanitize sensitive data
                                temp_json_path = temp_dir_path / arcname
                                temp_json_path.parent.mkdir(parents=True, exist_ok=True)

                                try:
                                    with open(file_path, "r", encoding="utf-8") as f:
                                        json_data = json.load(f)

                                    # Remove sensitive data
                                    sanitized_data = self._sanitize_json_config(
                                        json_data
                                    )

                                    with open(
                                        temp_json_path, "w", encoding="utf-8"
                                    ) as f:
                                        json.dump(sanitized_data, f, indent=4)

                                    zipf.write(temp_json_path, arcname)
                                    files_added += 1
                                except Exception as e:
                                    # If we can't parse the JSON, skip it
                                    continue

                if files_added == 0:
                    os.unlink(temp_zip_path)
                    return (
                        False,
                        "No log or configuration files found in experiment folder.",
                    )

            # Check file size (5MB limit)
            file_size = os.path.getsize(temp_zip_path)
            max_size = 5 * 1024 * 1024  # 5MB in bytes

            if file_size > max_size:
                os.unlink(temp_zip_path)
                size_mb = file_size / (1024 * 1024)
                return (
                    False,
                    f"Compressed file is too large ({size_mb:.1f}MB). Maximum allowed size is 5MB. Please contact the YSocial team for further support at {SUPPORT_EMAIL}",
                )

            # Prepare multipart form data
            timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

            with open(temp_zip_path, "rb") as f:
                files = {
                    "file": (
                        f"experiment_{experiment_id}_logs.zip",
                        f,
                        "application/zip",
                    )
                }
                data = {
                    "uiid": self.uuid,
                    "timestamp": timestamp,
                    "experiment_id": str(experiment_id),
                }

                # Add problem description if provided
                if problem_description:
                    data["problem_description"] = problem_description

                try:
                    response = requests.post(
                        f"http://{self.host}:{self.port}/api/errors",
                        files=files,
                        data=data,
                        timeout=30,
                    )

                    # Clean up temp files
                    os.unlink(temp_zip_path)
                    if temp_dir and os.path.exists(temp_dir):
                        shutil.rmtree(temp_dir, ignore_errors=True)

                    if response.status_code == 200:
                        return (
                            True,
                            "Experiment logs submitted successfully. Thank you for helping improve YSocial!",
                        )
                    else:
                        return (
                            False,
                            f"Telemetry server returned error: {response.status_code}. Please check your telemetry configuration or contact support at {SUPPORT_EMAIL}",
                        )

                except requests.exceptions.RequestException as e:
                    try:
                        os.unlink(temp_zip_path)
                    except OSError:
                        pass
                    if temp_dir and os.path.exists(temp_dir):
                        shutil.rmtree(temp_dir, ignore_errors=True)
                    return False, f"Failed to send logs: {str(e)}"

        except Exception as e:
            # Clean up temp files if they exist
            if temp_zip_path and os.path.exists(temp_zip_path):
                try:
                    os.unlink(temp_zip_path)
                except OSError:
                    pass
            if temp_dir and os.path.exists(temp_dir):
                try:
                    shutil.rmtree(temp_dir, ignore_errors=True)
                except OSError:
                    pass
            return False, f"Error preparing logs: {str(e)}"

    def _sanitize_json_config(self, data):
        """
        Remove sensitive information (URLs and API keys) from configuration JSON.

        :param data: JSON data (dict, list, or primitive)
        :return: Sanitized JSON data with sensitive fields removed
        """
        if isinstance(data, dict):
            sanitized = {}
            for key, value in data.items():
                # Remove fields that contain sensitive data
                key_lower = key.lower()
                if any(
                    sensitive in key_lower
                    for sensitive in [
                        "api_key",
                        "apikey",
                        "api-key",
                        "key",
                        "token",
                        "password",
                        "secret",
                    ]
                ):
                    sanitized[key] = "***REDACTED***"
                elif any(
                    url_field in key_lower
                    for url_field in ["url", "uri", "endpoint", "host", "api"]
                ):
                    # For URL-like fields, check if it's actually a URL string
                    if isinstance(value, str) and (
                        "http://" in value or "https://" in value or "://" in value
                    ):
                        sanitized[key] = "***REDACTED***"
                    else:
                        # Recursively sanitize non-URL values
                        sanitized[key] = self._sanitize_json_config(value)
                else:
                    # Check if the value itself is a URL string (regardless of key name)
                    if isinstance(value, str) and (
                        "http://" in value or "https://" in value
                    ):
                        sanitized[key] = "***REDACTED***"
                    else:
                        # Recursively sanitize other values
                        sanitized[key] = self._sanitize_json_config(value)
            return sanitized
        elif isinstance(data, list):
            return [self._sanitize_json_config(item) for item in data]
        else:
            # Primitive types (str, int, bool, None, etc.) are returned as-is
            # unless they look like URLs
            if isinstance(data, str) and ("http://" in data or "https://" in data):
                return "***REDACTED***"
            return data

    def _anonymize_log_line(self, line):
        """
        Anonymize file paths and sensitive information in a single log line.
        Similar to __anonymize_traceback but for general log lines.

        :param line: Single line from a log file
        :return: Anonymized line
        """
        # Pattern for file paths in logs (common formats)
        # Matches: /path/to/file.py, C:\path\to\file.py, etc.
        path_pattern = re.compile(r'File ".*?([^/\\]+)", line (\d+), in (.*)')
        # Home/installation path pattern
        home_pattern = re.compile(re.escape(str(sys.path[0])), re.IGNORECASE)
        # Generic absolute path patterns (more specific matching)
        # Unix path: /path/to/file.ext or /path/to/dir/
        unix_path_pattern = re.compile(r"(/(?:[a-zA-Z0-9_\-./]+/)+[a-zA-Z0-9_\-.]+)")
        # Windows path: C:\path\to\file.ext or C:\path\to\dir\
        windows_path_pattern = re.compile(
            r"([A-Za-z]:\\(?:[a-zA-Z0-9_\-\\.]+\\)*[a-zA-Z0-9_\-.]+)"
        )

        # Check for Python traceback-style file references first
        match = path_pattern.search(line)
        if match:
            filename, lineno, func = match.groups()
            return f'File "<anon>/{filename}", line {lineno}, in {func}\n'

        # Replace home/installation paths
        line = home_pattern.sub("<anon_path>", line)

        # Replace Windows absolute paths (do this first as it's more specific)
        def replace_windows_path(match):
            full_path = match.group(1)
            # Use the last component after splitting by backslash
            basename = full_path.split("\\")[-1]
            return f"<anon_path>\\{basename}"

        line = windows_path_pattern.sub(replace_windows_path, line)

        # Replace Unix absolute paths
        def replace_unix_path(match):
            full_path = match.group(1)
            # Use the last component after splitting by forward slash
            basename = full_path.split("/")[-1]
            return f"<anon_path>/{basename}"

        line = unix_path_pattern.sub(replace_unix_path, line)

        return line

    def __anonymize_traceback(self, exc) -> str:
        """
        Anonymize file paths in a traceback to protect user privacy.
        :param exc: Exception object or string representation of the traceback.
        :return:
        """
        if isinstance(exc, BaseException):
            tb_lines = traceback.format_exception(type(exc), exc, exc.__traceback__)
        elif isinstance(exc, str):
            tb_lines = exc.splitlines(keepends=True)
        else:
            return "<invalid stacktrace>"

        anonymized_lines = []
        path_pattern = re.compile(r'File ".*?([^/\\]+)", line (\d+), in (.*)')
        home_pattern = re.compile(re.escape(str(sys.path[0])), re.IGNORECASE)

        for line in tb_lines:
            match = path_pattern.search(line)
            if match:
                filename, lineno, func = match.groups()
                anonymized_lines.append(
                    f'File "<anon>/{filename}", line {lineno}, in {func}\n'
                )
            else:
                line = home_pattern.sub("<anon_path>", line)
                anonymized_lines.append(line)

        return "".join(anonymized_lines)
