#!/usr/bin/env python3
"""
Client process runner script for YSocial.
This script is invoked as a subprocess to run client simulations.
It's designed to be called by start_client using subprocess.Popen.
"""
import argparse
import sys


def main():
    """Main entry point for client process runner."""
    parser = argparse.ArgumentParser(
        description="Run YSocial client simulation process"
    )
    parser.add_argument("--exp-id", required=True, type=int, help="Experiment ID")
    parser.add_argument("--client-id", required=True, type=int, help="Client ID")
    parser.add_argument(
        "--population-id", required=True, type=int, help="Population ID"
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        default=False,
        help="Resume from last state (default: False)",
    )
    parser.add_argument(
        "--no-resume",
        dest="resume",
        action="store_false",
        help="Do not resume from last state",
    )
    parser.add_argument(
        "--db-type", default="sqlite", help="Database type (sqlite or postgresql)"
    )

    args = parser.parse_args()

    # Import the start_client_process function
    from y_web.utils.external_processes import start_client_process

    # Create minimal objects with just the IDs needed by start_client_process
    # The function will re-fetch the full objects from the database
    class MinimalObject:
        pass

    exp = MinimalObject()
    exp.idexp = args.exp_id

    cli = MinimalObject()
    cli.id = args.client_id

    population = MinimalObject()
    population.id = args.population_id

    # Call start_client_process with the parameters
    try:
        start_client_process(exp, cli, population, args.resume, args.db_type)
    except Exception as e:
        print(f"ERROR in client process: {e}", file=sys.stderr)
        import traceback

        traceback.print_exc(file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
