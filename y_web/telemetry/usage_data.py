import json
import os
import re
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
    def __init__(self, host="localhost", port=9000, user=None):
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

    def submit_experiment_logs(self, experiment_id, experiment_folder_path):
        """
        Compress and send experiment log files and configuration to telemetry server.
        
        :param experiment_id: ID of the experiment
        :param experiment_folder_path: Path to the experiment folder containing logs and configs
        :return: tuple (success: bool, message: str)
        """
        if not self.enabled:
            return False, "Telemetry is disabled. Please enable it in your user settings."
        
        temp_zip_path = None
        try:
            experiment_path = Path(experiment_folder_path)
            
            if not experiment_path.exists():
                return False, f"Experiment folder not found: {experiment_folder_path}"
            
            # Create a temporary zip file
            with tempfile.NamedTemporaryFile(suffix='.zip', delete=False) as temp_zip:
                temp_zip_path = temp_zip.name
            
            # Compress log files and JSON configuration files
            with zipfile.ZipFile(temp_zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                files_added = 0
                for file_path in experiment_path.rglob('*'):
                    if file_path.is_file():
                        # Include .log files and .json configuration files
                        if file_path.suffix.lower() in ['.log', '.json']:
                            # Add file to zip with relative path
                            arcname = file_path.relative_to(experiment_path)
                            zipf.write(file_path, arcname)
                            files_added += 1
                
                if files_added == 0:
                    os.unlink(temp_zip_path)
                    return False, "No log or configuration files found in experiment folder."
            
            # Check file size (10MB limit)
            file_size = os.path.getsize(temp_zip_path)
            max_size = 10 * 1024 * 1024  # 10MB in bytes
            
            if file_size > max_size:
                os.unlink(temp_zip_path)
                size_mb = file_size / (1024 * 1024)
                return False, f"Compressed file is too large ({size_mb:.1f}MB). Maximum allowed size is 10MB. Please contact the YSocial team for further support at {SUPPORT_EMAIL}"
            
            # Prepare multipart form data
            timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            
            with open(temp_zip_path, 'rb') as f:
                files = {'file': (f'experiment_{experiment_id}_logs.zip', f, 'application/zip')}
                data = {
                    'uiid': self.uuid,
                    'timestamp': timestamp,
                    'experiment_id': str(experiment_id)
                }
                
                try:
                    response = requests.post(
                        f"http://{self.host}:{self.port}/api/errors",
                        files=files,
                        data=data,
                        timeout=30
                    )
                    
                    # Clean up temp file
                    os.unlink(temp_zip_path)
                    
                    if response.status_code == 200:
                        return True, "Experiment logs submitted successfully. Thank you for helping improve YSocial!"
                    else:
                        return False, f"Server returned error: {response.status_code}"
                        
                except requests.exceptions.RequestException as e:
                    try:
                        os.unlink(temp_zip_path)
                    except OSError:
                        pass
                    return False, f"Failed to send logs: {str(e)}"
                    
        except Exception as e:
            # Clean up temp file if it exists
            if temp_zip_path and os.path.exists(temp_zip_path):
                try:
                    os.unlink(temp_zip_path)
                except OSError:
                    pass
            return False, f"Error preparing logs: {str(e)}"

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
