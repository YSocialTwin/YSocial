import json
import re
import sys
import traceback

import requests

from y_web.pyinstaller_utils import installation_id


class Telemetry(object):

    def __init__(self, host="localhost", port=9000):
        self.host = host
        self.port = port

        config_dir = installation_id.get_installation_config_dir()
        id_file = config_dir / "installation_id.json"

        if id_file.exists():
            try:
                with open(id_file, "r") as f:
                    installation_info = json.load(f)
                    self.uiid = installation_info.get("installation_id", None)
            except Exception:
                self.uiid = None

    def register_update_app(self, data, action="register"):
        """
        Register or update app installation on telemetry server using endpoints
        :param data:
        :param action:
        :return:
        """

        try:
            config_dir = installation_id.get_installation_config_dir()
            id_file = config_dir / "installation_id.json"
            with open(id_file, "r") as f:
                data = json.load(f)
                if action == "register":
                    data["action"] = "register"
                    data = json.dumps(data)
                    response = requests.post(
                        f"http://{self.host}:{self.port}/register", json=data
                    )
                elif action == "update":
                    data["action"] = "update"
                    response = requests.post(
                        f"http://{self.host}:{self.port}/register", json=data
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
        data["uiid"] = self.uuid
        try:
            data = json.dumps(data)
            response = requests.post(
                f"http://{self.host}:{self.port}/log_event", json=data
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

        stacktrace = data["stacktrace"]
        safe_trace = self.__anonymize_traceback(stacktrace)
        data["stacktrace"] = safe_trace
        data["uiid"] = self.uuid
        data = json.dumps(data)
        try:
            response = requests.post(
                f"http://{self.host}:{self.port}/log_stack_trace", json=data
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
