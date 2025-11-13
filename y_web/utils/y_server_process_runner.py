#!/usr/bin/env python3
"""
Server process runner script for YSocial.
This script is invoked as a subprocess to run the YServer.
It's designed to be called by start_server using subprocess.Popen.
"""
import argparse
import json
import os
import sys


def main():
    """Main entry point for server process runner."""
    parser = argparse.ArgumentParser(
        description="Run YSocial server simulation process"
    )
    parser.add_argument(
        "-c",
        "--config",
        required=True,
        help="Path to server configuration JSON file",
    )
    parser.add_argument(
        "--platform",
        required=True,
        choices=["microblogging", "forum"],
        help="Platform type (microblogging or forum)",
    )

    args = parser.parse_args()

    # Determine the correct server module based on platform
    if args.platform == "microblogging":
        # Add YServer to sys.path for imports
        from y_web.utils.path_utils import get_base_path

        base_path = get_base_path()
        yserver_path = os.path.join(base_path, "external", "YServer")
        sys.path.insert(0, yserver_path)
    elif args.platform == "forum":
        # Add YServerReddit to sys.path for imports
        from y_web.utils.path_utils import get_base_path

        base_path = get_base_path()
        yserver_path = os.path.join(base_path, "external", "YServerReddit")
        sys.path.insert(0, yserver_path)
    else:
        raise NotImplementedError(f"Unsupported platform {args.platform}")

    # Load configuration
    config = json.load(open(args.config, "r"))

    # Import and start the server
    print(f"Starting YServer for {args.platform}...", config)
    from y_server import app

    debug = False
    app.config["perspective_api"] = config["perspective_api"]
    app.config["sentiment_annotation"] = config["sentiment_annotation"]
    app.config["emotion_annotation"] = config["emotion_annotation"]
    app.run(debug=debug, port=int(config["port"]), host=config["host"])


if __name__ == "__main__":
    main()
