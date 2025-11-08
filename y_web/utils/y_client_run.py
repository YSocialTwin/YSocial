#!/usr/bin/env python3
"""
Client runner script for YSocial.
This script runs a client simulation in a subprocess.
"""
import argparse
import json
import os
import sys


def main():
    """Main entry point for client runner."""
    parser = argparse.ArgumentParser(description="Run YSocial client simulation")
    parser.add_argument("-c", "--config", required=True, help="Path to client configuration JSON file")
    parser.add_argument("--exp-id", required=True, help="Experiment ID")
    parser.add_argument("--client-id", required=True, help="Client ID", type=int)
    parser.add_argument("--population-id", required=True, help="Population ID", type=int)
    parser.add_argument("--resume", action="store_true", default=True, help="Resume from last state")
    parser.add_argument("--db-type", default="sqlite", help="Database type (sqlite or postgresql)")
    
    args = parser.parse_args()
    
    # Load configuration
    with open(args.config, 'r') as f:
        config = json.load(f)
    
    # Import here to avoid circular imports
    from y_web import create_app, db
    from y_web.models import Experiment, Client, Population, Client_Execution
    from y_web.utils.external_processes import run_client_simulation
    
    # Create app context
    app = create_app(args.db_type)
    
    with app.app_context():
        # Load database objects
        exp = db.session.query(Experiment).filter_by(id=args.exp_id).first()
        if not exp:
            print(f"ERROR: Experiment {args.exp_id} not found")
            sys.exit(1)
            
        cli = db.session.query(Client).filter_by(id=args.client_id).first()
        if not cli:
            print(f"ERROR: Client {args.client_id} not found")
            sys.exit(1)
            
        population = db.session.query(Population).filter_by(id=args.population_id).first()
        if not population:
            print(f"ERROR: Population {args.population_id} not found")
            sys.exit(1)
        
        # Run the simulation
        run_client_simulation(
            exp=exp,
            cli=cli,
            population=population,
            config_file=config,
            resume=args.resume
        )


if __name__ == "__main__":
    main()
