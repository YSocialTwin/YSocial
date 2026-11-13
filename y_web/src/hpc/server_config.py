"""The server configuration copied with an experiment folder of an HPC platform."""

import json
import os


def rewrite_server_config(
    new_folder: str, new_exp_name: str, new_db_uri: str, new_data_path: str
) -> None:
    """Point the copied ``server_config.json`` at the new folder; the run configuration is unchanged."""
    path = os.path.join(new_folder, "server_config.json")
    with open(path, "r", encoding="utf-8") as handle:
        config = json.load(handle)
    config["experiment_name"] = new_exp_name
    config["database_uri"] = new_db_uri
    config["data_path"] = new_data_path
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(config, handle, indent=2)
