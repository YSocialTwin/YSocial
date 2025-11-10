#!/usr/bin/env python3
"""
Client process runner script for YSocial.
This script is invoked as a subprocess to run client simulations.
It's designed to be called by start_client using subprocess.Popen.
"""
import argparse
import random
import sys
import traceback
from collections import defaultdict

import numpy as np

from y_web.models import (
    ActivityProfile,
    PopulationActivityProfile,
)


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
    # from y_web.utils.external_processes import start_client_process

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

        traceback.print_exc(file=sys.stderr)
        sys.exit(1)


def start_client_process(exp, cli, population, resume=True, db_type="sqlite"):
    """
    Start client simulation without pushing Flask app context.
    Independent of the main Flask runtime.
    """
    import json
    import os
    import sys

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from y_web import create_app, db  # only to reuse URI config
    from y_web.models import Client, Client_Execution, Exps, Population
    from y_web.utils.path_utils import get_base_path, get_writable_path

    # Create app only to get DB URI, but don't push its context
    app2 = create_app(db_type)
    db_uri = app2.config["SQLALCHEMY_DATABASE_URI"]

    # Build an independent SQLAlchemy engine/session
    engine = create_engine(db_uri, pool_pre_ping=True)
    Session = sessionmaker(bind=engine)
    session = Session()

    try:
        # Retrieve data fresh from DB (no app context)
        exp = session.query(Exps).get(exp.idexp)
        cli = session.query(Client).get(cli.id)
        population = session.query(Population).get(population.id)

        # Get base path (PyInstaller-aware) for reading bundled resources
        base_path = get_base_path()
        
        # Get writable path for experiment data (where experiments are stored)
        writable_base = get_writable_path()

        # Add external client modules to path
        if exp.platform_type == "microblogging":
            sys.path.append(os.path.join(base_path, 'external', 'YClient'))
            from y_client.clients import YClientWeb
        elif exp.platform_type == "forum":
            sys.path.append(os.path.join(base_path, 'external', 'YClientReddit'))
            from y_client.clients import YClientWeb
        else:
            raise NotImplementedError(f"Unsupported platform {exp.platform_type}")

        # Base directory for experiment data (writable location)
        BASE_DIR = os.path.join(writable_base, 'y_web')

        if "experiments_" in exp.db_name:
            uid = exp.db_name.removeprefix("experiments_")
            filename = os.path.join(BASE_DIR, 'experiments', uid, f"{population.name.replace(' ', '')}.json")
        else:
            uid = exp.db_name.split(os.sep)[1]
            filename = os.path.join(BASE_DIR, exp.db_name.split('database_server.db')[0], f"{population.name.replace(' ', '')}.json")

        data_base_path = os.path.join(BASE_DIR, 'experiments', uid) + os.sep
        config_file = json.load(
            open(os.path.join(data_base_path, f"client_{cli.name}-{population.name}.json"))
        )

        print("Starting client process...")

        ce = session.query(Client_Execution).filter_by(client_id=cli.id).first()
        print(f"Client {cli.name} execution record: {ce}")

        if ce:
            first_run = False
        else:
            print(f"Client {cli.name} first execution.")
            first_run = True
            ce = Client_Execution(
                client_id=cli.id,
                elapsed_time=0,
                expected_duration_rounds=cli.days * 24,
                last_active_hour=-1,
                last_active_day=-1,
            )
            session.add(ce)
            session.commit()

        log_file = f"{data_base_path}{cli.name}_client.log"
        if first_run and cli.network_type:
            path = f"{cli.name}_network.csv"
            cl = YClientWeb(
                config_file,
                data_base_path,
                first_run=first_run,
                network=path,
                log_file=log_file,
                llm=exp.llm_agents_enabled,
            )
        else:
            cl = YClientWeb(
                config_file,
                data_base_path,
                first_run=first_run,
                log_file=log_file,
                llm=exp.llm_agents_enabled,
            )

        if resume:
            cl.days = int((ce.expected_duration_rounds - ce.elapsed_time) / 24)

        cl.read_agents()
        cl.add_feeds()

        if first_run and cli.network_type:
            cl.add_network()

        if not os.path.exists(filename):
            cl.save_agents(filename)

        run_simulation(cl, cli.id, filename, exp, population)

    finally:
        session.close()
        engine.dispose()


def get_users_per_hour(population, agents, session):
    # get population activity profiles
    activity_profiles = defaultdict(list)
    population_activity_profiles = (
        session.query(PopulationActivityProfile)
        .filter(PopulationActivityProfile.population == population.id)
        .all()
    )
    for ap in population_activity_profiles:
        profile = (
            session.query(ActivityProfile)
            .filter(ActivityProfile.id == ap.activity_profile)
            .first()
        )
        activity_profiles[profile.name] = [int(x) for x in profile.hours.split(",")]

    hours_to_users = defaultdict(list)
    for ag in agents:
        profile = activity_profiles[ag.activity_profile]

        for h in profile:
            hours_to_users[h].append(ag)

    return hours_to_users


def sample_agents(agents, expected_active_users):
    weights = [a.daily_activity_level for a in agents]
    # normalize weights to sum to 1
    weights = [w / sum(weights) for w in weights]

    try:
        sagents = np.random.choice(
            agents,
            size=expected_active_users,
            p=weights,
            replace=False,
        )
    except Exception:
        sagents = np.random.choice(agents, size=expected_active_users, replace=False)

    return sagents


def run_simulation(cl, cli_id, agent_file, exp, population):
    """
    Run the simulation
    """
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from y_web import create_app, db  # only to reuse URI config
    from y_web.models import Client, Client_Execution, Exps, Population

    # Create app only to get DB URI, but don't push its context
    app2 = create_app("sqlite")
    db_uri = app2.config["SQLALCHEMY_DATABASE_URI"]

    # Build an independent SQLAlchemy engine/session
    engine = create_engine(db_uri, pool_pre_ping=True)
    Session = sessionmaker(bind=engine)
    session = Session()

    platform_type = exp.platform_type

    total_days = int(cl.days)
    daily_slots = int(cl.slots)

    page_agents = [p for p in cl.agents.agents if p.is_page]

    hour_to_page = get_users_per_hour(population, page_agents, session)

    for d1 in range(total_days):
        common_agents = [p for p in cl.agents.agents if not p.is_page]
        hour_to_users = get_users_per_hour(population, common_agents, session)

        daily_active = {}
        tid, _, _ = cl.sim_clock.get_current_slot()

        for _ in range(daily_slots):
            tid, d, h = cl.sim_clock.get_current_slot()

            # get expected active users for this time slot considering the global population (at least 1)
            expected_active_users = max(
                int(len(cl.agents.agents) * cl.hourly_activity[str(h)]), 1
            )

            # take the minimum between expected active over the whole population and available users at time h
            expected_active_users = min(expected_active_users, len(hour_to_users[h]))

            # get active pages at this hour
            active_pages = hour_to_page[h]

            if platform_type == "microblogging":
                # pages post all the time their activity profile is active
                for page in active_pages:
                    page.select_action(
                        tid=tid,
                        actions=[],
                        max_length_thread_reading=cl.max_length_thread_reading,
                    )

                # check whether there are agents left
            if len(cl.agents.agents) == 0:
                break

            # get the daily activities of each agent
            try:
                sagents = sample_agents(hour_to_users[h], expected_active_users)
            except Exception as e:
                # case of no active agents at this hour
                sagents = []

            # shuffle agents
            random.shuffle(sagents)

            ################# PARALLELIZED SECTION #################
            # def agent_task(g, tid):
            for g in sagents:
                acts = [a for a, v in cl.actions_likelihood.items() if v > 0]

                daily_active[g.name] = None

                # Get a random integer within g.round_actions.
                # If g.is_page == 1, then rounds = 0 (the page does not perform actions)
                if g.is_page == 1:
                    rounds = 0
                else:
                    rounds = random.randint(1, int(g.round_actions))

                for _ in range(rounds):
                    # sample two elements from a list with replacement

                    candidates = random.choices(
                        acts,
                        k=2,
                        weights=[cl.actions_likelihood[a] for a in acts],
                    )
                    candidates.append("NONE")

                    try:
                        # reply to received mentions
                        if g not in cl.pages:
                            g.reply(tid=tid)

                        # select action to be performed
                        g.select_action(
                            tid=tid,
                            actions=candidates,
                            max_length_thread_reading=cl.max_length_thread_reading,
                        )
                    except Exception as e:
                        print(f"Error ({g.name}): {e}")
                        print(traceback.format_exc())
                        pass

            # Run agent tasks in parallel
            # with concurrent.futures.ThreadPoolExecutor() as executor:
            #    executor.map(agent_task, sagents)
            ################# END OF PARALLELIZATION #################

            # increment slot
            cl.sim_clock.increment_slot()

            # update client execution object
            ce = session.query(Client_Execution).filter_by(client_id=cli_id).first()
            if ce:
                ce.elapsed_time += 1
                ce.last_active_hour = h
                ce.last_active_day = d
                session.add(ce)  # Explicitly mark as modified for PostgreSQL
                session.commit()

        # evaluate follows (once per day, only for a random sample of daily active agents)
        if float(cl.config["agents"]["probability_of_daily_follow"]) > 0:
            da = [
                agent
                for agent in cl.agents.agents
                if agent.name in daily_active
                and agent not in cl.pages
                and random.random()
                < float(cl.config["agents"]["probability_of_daily_follow"])
            ]

            # Evaluating new friendship ties
            for agent in da:
                if agent not in cl.pages:
                    agent.select_action(tid=tid, actions=["FOLLOW", "NONE"])

        # daily churn and new agents
        if len(daily_active) > 0:
            # daily churn
            cl.churn(tid)

            # daily new agents
            if cl.percentage_new_agents_iteration > 0:
                for _ in range(
                    max(
                        1,
                        int(len(daily_active) * cl.percentage_new_agents_iteration),
                    )
                ):
                    cl.add_agent()

        # saving "living" agents at the end of the day
        cl.save_agents(agent_file)

    session.close()
    engine.dispose()


if __name__ == "__main__":
    main()
