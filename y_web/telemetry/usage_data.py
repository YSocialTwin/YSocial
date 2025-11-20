import json
import re
import sys
import traceback
from datetime import datetime, timezone

import requests

from y_web.pyinstaller_utils import installation_id


class Telemetry(object):

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
