#!/usr/bin/env python3
"""
Client process runner script for YSocial.
This script is invoked as a subprocess to run client simulations.
It's designed to be called by start_client using subprocess.Popen.
"""

import argparse
import json
import math
import os
import random
import re
import sys
import traceback
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

import numpy as np

from y_web.models import (
    ActivityProfile,
    PopulationActivityProfile,
)

# Number of days to run an infinite client per iteration before checking for termination
# Infinite clients run for this many days, then loop back to continue running
INFINITE_CLIENT_ITERATION_DAYS = 365


def _get_client_archetypes(client):
    """Return a normalized archetype config for clients that may not implement it."""
    archetypes = getattr(client, "agent_archetypes", None)
    if archetypes:
        return archetypes
    return {
        "enabled": False,
        "distribution": {},
        "transitions": {},
    }


def _resolve_client_package_dir(base_path, platform_type):
    """Resolve the external client package directory for a platform."""
    if platform_type == "microblogging":
        return os.path.join(base_path, "external", "YClient")
    if platform_type == "forum":
        return os.path.join(base_path, "external", "YClientReddit")
    raise NotImplementedError(f"Unsupported platform {platform_type}")


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

        # Add platform-specific external client modules ahead of any other y_client package.
        client_package_dir = _resolve_client_package_dir(base_path, exp.platform_type)
        if client_package_dir in sys.path:
            sys.path.remove(client_package_dir)
        sys.path.insert(0, client_package_dir)
        from y_client.clients import YClientWeb

        # Base directory for experiment data (writable location)
        BASE_DIR = os.path.join(writable_base, "y_web")

        if "experiments_" in exp.db_name:
            uid = exp.db_name.removeprefix("experiments_")
        else:
            # db_name format: "experiments/uid/database_server.db" or with backslashes
            # Split on both / and \ to handle cross-platform path separators
            parts = re.split(r"[/\\]", exp.db_name)
            if len(parts) >= 2:
                uid = parts[1]  # Extract UID from path: experiments/{uid}/...
            else:
                raise ValueError(f"Invalid db_name format: {exp.db_name}")

        data_base_path = os.path.join(BASE_DIR, "experiments", uid) + os.sep

        from y_web.utils.experiment_schema import ensure_experiment_schema_for_uri
        ensure_experiment_schema_for_uri(f"sqlite:///{data_base_path}database_server.db")

        # Try to find the population file
        # The expected filename is {population.name}.json
        # However, due to population renaming during upload, the file may have
        # a different name (e.g., without the _2 suffix if uploaded before fix)
        expected_pop_file = os.path.join(
            data_base_path, f"{population.name.replace(' ', '')}.json"
        )

        if os.path.exists(expected_pop_file):
            filename = expected_pop_file
        else:
            # Fallback: search for a matching population file
            # Population files don't start with "client_" and end with ".json"
            filename = None
            pop_name_base = population.name.replace(" ", "")
            # Remove any _N suffix to find the base name
            base_match = re.match(r"^(.+?)(?:_\d+)?$", pop_name_base)
            if base_match:
                base_name = base_match.group(1)
                for f in os.listdir(data_base_path):
                    if (
                        f.endswith(".json")
                        and not f.startswith("client_")
                        and not f.startswith("config_")
                        and not f.startswith("prompts")
                        and f.startswith(base_name)
                    ):
                        filename = os.path.join(data_base_path, f)
                        print(
                            f"Warning: Expected population file not found. Using fallback: {f}",
                            file=sys.stderr,
                        )
                        break

            if filename is None:
                # Use the expected path (will fail when saving if not exists)
                filename = expected_pop_file

        # Try to find the client config file
        # The expected filename is client_{cli.name}-{population.name}.json
        # However, due to population renaming during upload, the file may have
        # a different name (e.g., without the _2 suffix if uploaded before fix)
        expected_client_file = os.path.join(
            data_base_path, f"client_{cli.name}-{population.name}.json"
        )

        print(
            f"Looking for client config file at: {expected_client_file}",
            file=sys.stderr,
        )

        if os.path.exists(expected_client_file):
            client_config_path = expected_client_file
        else:
            # Fallback: search for a matching client file by client name
            # This handles cases where population was renamed but files weren't
            client_config_path = None
            for f in os.listdir(data_base_path):
                if f.startswith(f"client_{cli.name}-") and f.endswith(".json"):
                    client_config_path = os.path.join(data_base_path, f)
                    print(
                        f"Warning: Expected file not found. Using fallback: {f}",
                        file=sys.stderr,
                    )
                    break

            if client_config_path is None:
                raise FileNotFoundError(
                    f"No client config file found for client '{cli.name}' in {data_base_path}, file=sys.stderr"
                )

        config_file = json.load(open(client_config_path))

        print("Starting client process...", file=sys.stderr)

        print(f"Looking up Client_Execution for client_id={cli.id}", file=sys.stderr)
        ce = session.query(Client_Execution).filter_by(client_id=cli.id).first()
        print(
            f"Client {cli.name} (id={cli.id}) execution record: {ce}", file=sys.stderr
        )
        if ce:
            print(
                f"  Execution record details: elapsed_time={ce.elapsed_time}, expected_duration={ce.expected_duration_rounds}",
                file=sys.stderr,
            )

        if ce:
            first_run = False
        else:
            print(f"Client {cli.name} first execution.")
            first_run = True
            # For infinite clients (days = -1), set expected_duration_rounds to -1
            expected_rounds = -1 if cli.days == -1 else cli.days * 24
            ce = Client_Execution(
                client_id=cli.id,
                elapsed_time=0,
                expected_duration_rounds=expected_rounds,
                last_active_hour=-1,
                last_active_day=-1,
            )
            session.add(ce)
            session.commit()

        log_file = f"{data_base_path}{cli.name}_client.log"

        print(f"Log file for client {cli.name}: {log_file}", file=sys.stderr)
        print(f"Data base path: {data_base_path}", file=sys.stderr)

        # Check if this is an infinite client
        is_infinite = cli.days == -1 or ce.expected_duration_rounds == -1

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
            print(f"First run (with network)", file=sys.stderr)
        else:
            cl = YClientWeb(
                config_file,
                data_base_path,
                first_run=first_run,
                log_file=log_file,
                llm=exp.llm_agents_enabled,
            )
            if first_run:
                print(f"First run (without network)", file=sys.stderr)
            else:
                print(f"Resuming run", file=sys.stderr)

        if resume and not is_infinite:
            remaining_rounds = ce.expected_duration_rounds - ce.elapsed_time
            # If we've already reached or exceeded expected duration, don't run
            if remaining_rounds <= 0:
                print(
                    f"Client already completed (elapsed: {ce.elapsed_time}, expected: {ce.expected_duration_rounds})",
                    file=sys.stderr,
                )
                return
            # Use math.ceil to ensure at least 1 day is processed when there are
            # remaining rounds. Using int() would result in 0 days when remaining
            # rounds < 24, causing the simulation to skip the final hours.
            cl.days = max(1, math.ceil(remaining_rounds / 24))
        elif is_infinite:
            # For infinite clients, run for a longer period per iteration
            # The client will continue running until manually stopped
            print(f"Infinite client - running until manually stopped", file=sys.stderr)
            cl.days = INFINITE_CLIENT_ITERATION_DAYS

        cl.read_agents()
        cl.add_feeds()

        print(f"Loaded {len(cl.agents.agents)} agents.", file=sys.stderr)

        if first_run and cli.network_type:
            cl.add_network()

        if not os.path.exists(filename):
            # Ensure all agents have archetype before saving
            ensure_agents_have_archetype(cl.agents.agents, _get_client_archetypes(cl))
            cl.save_agents(filename)

        run_simulation(cl, cli.id, filename, exp, population, db_type)

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
        # Check if agent has activity_profile attribute
        if not hasattr(ag, "activity_profile"):
            print(
                f"Warning: Agent {ag.name} (is_page={getattr(ag, 'is_page', 'unknown')}) missing activity_profile attribute",
                file=sys.stderr,
            )
            continue

        if ag.activity_profile is None:
            print(
                f"Warning: Agent {ag.name} (is_page={getattr(ag, 'is_page', 'unknown')}) has None activity_profile",
                file=sys.stderr,
            )
            continue

        # Use get with default to handle missing profiles gracefully
        profile = activity_profiles.get(ag.activity_profile)
        if profile is None:
            # If profile not found, try to fetch it directly from database
            try:
                profile_obj = (
                    session.query(ActivityProfile)
                    .filter(ActivityProfile.id == ag.activity_profile)
                    .first()
                )
                if profile_obj:
                    profile = [int(x) for x in profile_obj.hours.split(",")]
                    activity_profiles[ag.activity_profile] = profile
                    print(
                        f"Info: Loaded activity profile {ag.activity_profile} for agent {ag.name} (is_page={getattr(ag, 'is_page', 'unknown')})",
                        file=sys.stderr,
                    )
                else:
                    # Profile doesn't exist, skip this agent
                    print(
                        f"Warning: Activity profile {ag.activity_profile} not found in database for agent {ag.name} (is_page={getattr(ag, 'is_page', 'unknown')})",
                        file=sys.stderr,
                    )
                    continue
            except Exception as e:
                print(
                    f"Warning: Error fetching activity profile for agent {ag.name}: {e}",
                    file=sys.stderr,
                )
                continue

        for h in profile:
            hours_to_users[h].append(ag)

    return hours_to_users


def sample_agents(agents, expected_active_users, archetypes=None):
    """
    Sample agents based on their daily activity level and archetype distribution.
    If archetypes are enabled, sample according to the specified distribution.
    Otherwise, sample based solely on daily activity levels.

    :param agents:
    :param expected_active_users:
    :param archetypes:
    :return:
    """
    sagents = []

    if archetypes["enabled"]:
        candidates_per_archetype = {}
        weights_per_archetype = {}
        # identify the percentages of each archetype
        user_types = {}
        for k, v in archetypes["distribution"].items():
            user_types[k] = max(int(v * expected_active_users), 1)

        for a in agents:
            # Use getattr with default to handle agents without archetype attribute (e.g., when resuming old simulations)
            # Default to 'broadcaster' as it's the most permissive archetype with full action capabilities
            agent_archetype = getattr(a, "archetype", "broadcaster")
            if agent_archetype not in candidates_per_archetype:
                candidates_per_archetype[agent_archetype] = []
                weights_per_archetype[agent_archetype] = []
            candidates_per_archetype[agent_archetype].append(a)
            weights_per_archetype[agent_archetype].append(a.daily_activity_level)

        for atype, count in user_types.items():
            if atype in candidates_per_archetype:
                cands = candidates_per_archetype[atype]
                wts = weights_per_archetype[atype]
                # normalize weights
                wts = [w / sum(wts) for w in wts]
                try:
                    sampled = np.random.choice(
                        cands,
                        size=min(count, len(cands)),
                        p=wts,
                        replace=False,
                    )
                except Exception:
                    sampled = np.random.choice(
                        cands,
                        size=min(count, len(cands)),
                        replace=False,
                    )
                sagents.extend(sampled)
    else:
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
            sagents = np.random.choice(
                agents, size=expected_active_users, replace=False
            )

    return sagents


def ensure_agents_have_archetype(agents, archetypes):
    """
    Ensure all agents have an archetype attribute before saving.
    If archetypes are enabled and an agent doesn't have an archetype,
    assign a default based on the archetype distribution.

    Pages are excluded from archetype assignment as they don't use the archetype system.

    :param agents: List of agent objects
    :param archetypes: Archetype configuration dict
    """
    if archetypes and archetypes.get("enabled", False):
        # Get distribution for weighted random assignment
        distribution = archetypes.get("distribution", {"broadcaster": 1.0})
        archetype_choices = list(distribution.keys())
        archetype_weights = list(distribution.values())

        for agent in agents:
            # Skip pages - they don't use archetypes
            if hasattr(agent, "is_page") and agent.is_page == 1:
                continue

            if not hasattr(agent, "archetype") or agent.archetype is None:
                # Assign archetype based on distribution
                agent.archetype = random.choices(
                    archetype_choices, weights=archetype_weights, k=1
                )[0]
                print(
                    f"Assigned archetype '{agent.archetype}' to agent {agent.name}",
                    file=sys.stderr,
                )


def process_agent(g, archetypes, cl, exp, tid, FakeAgent, local_random):
    """
    Process a single agent's actions for one time slot.

    :param g: The agent to process
    :param archetypes: Archetype configuration
    :param cl: Client instance
    :param exp: Experiment instance
    :param tid: Current time ID
    :param FakeAgent: FakeAgent class (for microblogging) or None
    :param local_random: Thread-local random.Random instance for thread safety
    :return: Tuple of (agent_name, success_flag)
    """

    try:
        if archetypes["enabled"]:
            # filtering the actions based on the archetype
            # Use getattr with default to handle agents without archetype attribute (e.g., when resuming old simulations)
            # Default to 'broadcaster' as it's the most permissive archetype with full action capabilities
            agent_archetype = getattr(g, "archetype", "broadcaster")
            if agent_archetype == "validator":
                acts = [
                    a
                    for a, v in cl.actions_likelihood.items()
                    if v > 0 and a in ["READ", "SHARE", "SEARCH"]
                ]
                if exp.platform_type == "microblogging":
                    g.__class__ = FakeAgent  # change class to FakeAgent to limit actions (only for microblogging)
            elif agent_archetype == "broadcaster":
                acts = [a for a, v in cl.actions_likelihood.items() if v > 0]
            elif agent_archetype == "explorer":
                acts = ["FOLLOW"]
                if exp.platform_type == "microblogging":
                    g.__class__ = FakeAgent  # change class to FakeAgent to limit actions (only for microblogging)

        else:
            acts = [a for a, v in cl.actions_likelihood.items() if v > 0]

        # Get a random integer within g.round_actions.
        # If g.is_page == 1, then rounds = 0 (the page does not perform actions)
        if g.is_page == 1:
            rounds = 1
        else:
            lower = max(int(g.round_actions) - 2, 1)
            rounds = local_random.randint(lower, int(g.round_actions))
            # Round_actions max is set for each agent by sampling from a user defined distribution.
            # Execute at least "lower" actions per user (to guarantee the activity level distribution).

        for _ in range(rounds):
            # sample two elements from a list with replacement
            if len(acts) > 1:
                candidates = local_random.choices(
                    acts,
                    k=2,
                    weights=[cl.actions_likelihood[a] for a in acts],
                )
                candidates.append("NONE")
            else:
                candidates = acts + ["NONE"]

            try:
                # reply to received mentions
                if g not in cl.pages:
                    if not archetypes["enabled"]:
                        g.reply(tid=tid)
                    else:
                        # Use getattr with default to handle agents without archetype attribute
                        if (
                            getattr(g, "archetype", "broadcaster") == "broadcaster"
                        ):  # only broadcasters reply
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

        return (g.name, True)
    except Exception as e:
        print(f"Error processing agent {g.name}: {e}", file=sys.stderr)
        print(traceback.format_exc(), file=sys.stderr)
        return (g.name, False)


def run_simulation(cl, cli_id, agent_file, exp, population, db_type):
    """
    Run the simulation
    """
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from y_web import create_app  # only to reuse URI config
    from y_web.models import Client_Execution
    from y_web.utils.path_utils import get_base_path

    base_path = get_base_path()
    FakeAgent = None
    if exp.platform_type == "microblogging":
        sys.path.append(os.path.join(base_path, "external", "YClient"))
        from y_client.classes import FakeAgent

    # Create app only to get DB URI, but don't push its context
    app2 = create_app(db_type)
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

    archetypes = _get_client_archetypes(cl)

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
                        actions=None,
                    )

            # check whether there are agents left
            if len(cl.agents.agents) == 0:
                break

            # get the daily activities of each agent (stratified on archetypes if enabled)
            try:
                sagents = sample_agents(
                    hour_to_users[h], expected_active_users, archetypes
                )
            except Exception as e:
                print(f"Error sampling agents: {e}", file=sys.stderr)
                sagents = []

            # shuffle agents
            random.shuffle(sagents)

            # Process agents in parallel using ThreadPoolExecutor
            # Only proceed if there are agents to process
            if len(sagents) > 0:
                # Use max_workers based on available CPUs, but cap it for resource management
                max_workers = min(
                    len(sagents), 10
                )  # Cap at 10 workers to avoid resource exhaustion

                # Process agents in parallel (FakeAgent was imported at function start)
                with ThreadPoolExecutor(max_workers=max_workers) as executor:
                    # Submit all agent processing tasks with thread-local random instances
                    # Create properly seeded Random instances for thread safety
                    future_to_agent = {
                        executor.submit(
                            process_agent,
                            g,
                            archetypes,
                            cl,
                            exp,
                            tid,
                            FakeAgent,
                            random.Random(random.randint(0, 2**32 - 1)),
                        ): g
                        for g in sagents
                    }

                    # Collect results as they complete
                    # Track all agents in daily_active, not just successful ones (preserves original behavior)
                    for future in as_completed(future_to_agent):
                        agent_name, success = future.result()
                        # Add to daily_active regardless of success to maintain original behavior
                        daily_active[agent_name] = None

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

                # Check if we've reached 100% completion (skip for infinite clients)
                # Infinite clients have expected_duration_rounds = -1
                if (
                    ce.expected_duration_rounds > 0
                    and ce.elapsed_time >= ce.expected_duration_rounds
                ):
                    print(
                        f"Client {cli_id} reached 100% completion (elapsed: {ce.elapsed_time}, expected: {ce.expected_duration_rounds})",
                        file=sys.stderr,
                    )

                    # Check if all clients in this experiment have completed
                    # Import Client model to check other clients
                    from y_web.models import Client, Exps

                    # Get current client to find experiment ID
                    client = session.query(Client).filter_by(id=cli_id).first()
                    if client:
                        # Use a single JOIN query to get all client execution records
                        # for this experiment. Exclude infinite clients (expected_duration_rounds = -1)
                        incomplete_clients = (
                            session.query(Client)
                            .join(
                                Client_Execution,
                                Client.id == Client_Execution.client_id,
                            )
                            .filter(Client.id_exp == client.id_exp)
                            .filter(
                                Client_Execution.expected_duration_rounds
                                > 0,  # Exclude infinite clients
                                Client_Execution.elapsed_time
                                < Client_Execution.expected_duration_rounds,
                            )
                            .count()
                        )

                        # Also check for clients without execution records
                        clients_without_exec = (
                            session.query(Client)
                            .outerjoin(
                                Client_Execution,
                                Client.id == Client_Execution.client_id,
                            )
                            .filter(Client.id_exp == client.id_exp)
                            .filter(Client_Execution.id == None)
                            .count()
                        )

                        # Check if there are any infinite clients still running
                        infinite_clients = (
                            session.query(Client)
                            .join(
                                Client_Execution,
                                Client.id == Client_Execution.client_id,
                            )
                            .filter(Client.id_exp == client.id_exp)
                            .filter(Client_Execution.expected_duration_rounds == -1)
                            .count()
                        )

                        all_completed = (
                            incomplete_clients == 0
                            and clients_without_exec == 0
                            and infinite_clients == 0
                        )

                        # If all clients are completed (no infinite clients), update experiment status to "completed"
                        if all_completed:
                            exp = (
                                session.query(Exps)
                                .filter_by(idexp=client.id_exp)
                                .first()
                            )
                            if exp:
                                exp.exp_status = "completed"
                                session.commit()
                                print(
                                    f"Experiment {client.id_exp} marked as completed",
                                    file=sys.stderr,
                                )

                    # Clean up and exit
                    session.close()
                    engine.dispose()
                    return

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

        # change the archetypes if enabled
        if d1 % 7 == 0 and d1 > 0:  # weekly changes
            if archetypes["enabled"]:
                for agent in cl.agents.agents:
                    # Use getattr with default to handle agents without archetype attribute
                    # Default to 'broadcaster' as it's the most permissive archetype with full action capabilities
                    current_archetype = getattr(agent, "archetype", "broadcaster")
                    probabilities = archetypes["transitions"][current_archetype]
                    choice = random.choices(
                        population=list(probabilities.keys()),
                        weights=list(probabilities.values()),
                        k=1,
                    )[0]
                    agent.archetype = choice

        # Ensure all agents have archetype before saving (handles new agents added during simulation)
        ensure_agents_have_archetype(cl.agents.agents, archetypes)

        # saving "living" agents at the end of the day
        cl.save_agents(agent_file)

    session.close()
    engine.dispose()


if __name__ == "__main__":
    main()
