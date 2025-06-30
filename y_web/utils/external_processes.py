import subprocess
import os
import re
import sys
from requests import post
import json
import time
import random
from multiprocessing import Process
import traceback
from y_web.models import (
    Client_Execution,
    Ollama_Pull, Exps,
)
from y_web import db, client_processes
import requests
from ollama import Client as oclient
import concurrent
import numpy as np


def terminate_process_on_port(port):
    """
    Terminate the process using the specified port

    :param port: the port number
    """
    try:
        result = subprocess.run(
            ["lsof", "-t", "-i", f":{port}"], capture_output=True, text=True, check=True
        )
        pid = result.stdout.strip()

        if pid:
            print(f"Found process {pid} using port {port}. Killing process...")
            os.kill(int(pid), 9)  # Send SIGKILL to the process
            print(f"Process {pid} terminated.")
        else:
            print(f"No process found using port {port}.")
    except Exception as e:
        print(f"Error: {e}")
        pass


def start_server(exp):
    """
    Start the y_server in a detached screen

    :param exp: the experiment object
    """
    yserver_path = os.path.dirname(os.path.abspath(__file__)).split("y_web")[0]
    sys.path.append(f"{yserver_path}{os.sep}external{os.sep}YServer{os.sep}")
    BASE_DIR = os.path.dirname(os.path.abspath(__file__)).split("utils")[0]
    config = f"{yserver_path}y_web{os.sep}{exp.db_name.split('database_server.db')[0]}config_server.json"
    exp_uid = exp.db_name.split(os.sep)[1]

    if exp.platform_type == "microblogging":
        flask_command = f"python {yserver_path}external{os.sep}YServer{os.sep}y_server_run.py -c {config}"
    elif exp.platform_type == "forum":
        flask_command = f"python {yserver_path}external{os.sep}YServerReddit{os.sep}y_server_run.py -c {config}"
    else:
        raise NotImplementedError(f"Unsupported platform {exp.platform_type}")

    # Check if pyenv is available and detect environment
    pyenv_env = None
    try:
        # Check if pyenv is installed
        subprocess.run(["pyenv", "--version"], capture_output=True, check=True)
        
        # Try to detect ysocial environment first
        result = subprocess.run(["pyenv", "versions"], capture_output=True, text=True, check=True)
        if "ysocial" in result.stdout:
            pyenv_env = "ysocial"
        else:
            # Get current pyenv environment
            result = subprocess.run(["pyenv", "version"], capture_output=True, text=True, check=True)
            current_env = result.stdout.strip().split()[0]
            if current_env != "system":
                pyenv_env = current_env
    except (subprocess.CalledProcessError, FileNotFoundError):
        # pyenv not available, use system python
        pass

    # Command to run in the detached screen
    if pyenv_env:
        # launch via a login shell so pyenv and environment are initialized
        screen_command = (
            f"screen -dmS {exp_uid} bash -lc \"pyenv activate {pyenv_env} && {flask_command}\""
        )
        print(f"Starting server with pyenv environment: {pyenv_env}")
    else:
        screen_command = f"screen -dmS {exp_uid} {flask_command}"
        print("Starting server with system python")
    print(f"Starting server for experiment {exp_uid}...")
    subprocess.run(screen_command, shell=True, check=True)

    # Wait for the server to start
    time.sleep(10)
    data = {"path": f"{BASE_DIR[1:]}{exp.db_name}"}
    headers = {"Content-Type": "application/json"}
    ns = f"http://{exp.server}:{exp.port}/change_db"
    post(f"{ns}", headers=headers, data=json.dumps(data))


def is_ollama_installed():
    # Step 1: Check if Ollama is installed
    try:
        subprocess.run(
            ["ollama", "--version"], capture_output=True, text=True, check=True
        )
        print("Ollama is installed.")
        return True
    except FileNotFoundError:
        print("Ollama is not installed.")
        return False
    except subprocess.CalledProcessError as e:
        print(f"Error checking Ollama installation: {e}")
        return False


def is_ollama_running():
    # Step 2: Check if Ollama is running
    try:
        response = requests.get("http://127.0.0.1:11434/api/version")
        if response.status_code == 200:
            print("Ollama is running.")
            return True
        else:
            print(
                f"Ollama responded but not running correctly. Status: {response.status_code}"
            )
            return False
    except requests.ConnectionError:
        print("Ollama is not running or cannot be reached.")
        return False


def start_ollama_server():
    if is_ollama_installed():
        if not is_ollama_running():
            screen_command = f"screen -dmS ollama ollama serve"

            print(f"Starting ollama server...")
            subprocess.run(screen_command, shell=True, check=True)

            # Wait for the server to start
            time.sleep(5)
        else:
            print("Ollama is already running.")
    else:
        print("Ollama is not installed.")


def pull_ollama_model(model_name):
    if is_ollama_running():
        process = Process(target=start_ollama_pull, args=(model_name,))
        process.start()
        client_processes[model_name] = process


def start_ollama_pull(model_name):
    ol_client = oclient(
        host="http://127.0.0.1:11434", headers={"x-some-header": "some-value"}
    )

    for progress in ol_client.pull(model_name, stream=True):
        model = Ollama_Pull.query.filter_by(model_name=model_name).first()
        if not model:
            model = Ollama_Pull(model_name=model_name, status=0)
            db.session.add(model)
            db.session.commit()

        total = progress.get("total")
        completed = progress.get("completed")
        if completed is not None:
            current = float(completed) / float(total)
            # update the model status
            model = Ollama_Pull.query.filter_by(model_name=model_name).first()
            model.status = current
            db.session.commit()


def get_ollama_models():
    pattern = r"model='(.*?)'"
    models = []

    ol_client = oclient(
        host="http://0.0.0.0:11434", headers={"x-some-header": "some-value"}
    )

    # Extract all model values
    for i in ol_client.list():
        models = re.findall(pattern, str(i))

    models = [m for m in models if len(m) > 0]
    return models


def delete_ollama_model(model_name):
    ol_client = oclient(
        host="http://0.0.0.0:11434", headers={"x-some-header": "some-value"}
    )

    ol_client.delete(model_name)


def delete_model_pull(model_name):
    if model_name in client_processes:
        process = client_processes[model_name]
        process.terminate()
        process.join()

    model = Ollama_Pull.query.filter_by(model_name=model_name).first()
    db.session.delete(model)
    db.session.commit()


def terminate_client(cli, pause=False):
    """
    Stop the y_client

    :param cli: the client object
    """
    process = client_processes[cli.name]
    process.terminate()
    process.join()

    # update client execution object
    if not pause:
        ce = Client_Execution.query.filter_by(client_id=cli.id).first()
        ce.expected_duration_rounds = 0
        ce.elapsed_time = 0
        db.session.commit()


def start_client(exp, cli, population, resume=False):
    process = Process(
        target=start_client_process,
        args=(
            exp,
            cli,
            population,
            resume,
        ),
    )
    process.start()
    client_processes[cli.name] = process


def start_client_process(exp, cli, population, resume=False):
    """
    Start the y_client

    :param exp:
    :param cli:
    :param population:
    :return:
    """

    yclient_path = os.path.dirname(os.path.abspath(__file__)).split("y_web")[0]

    if exp.platform_type == "microblogging":
        sys.path.append(f"{yclient_path}{os.sep}external{os.sep}YClient/")
        from y_client.clients import YClientWeb  # noqa: E402,F401

    elif exp.platform_type == "forum":
        sys.path.append(f"{yclient_path}{os.sep}external{os.sep}YClientReddit/")
        from y_client.clients import YClientWeb  # noqa: E402,F401
    else:
        raise NotImplementedError(f"Unsupported platform {exp.platform_type}")

    # get experiment base path
    BASE_DIR = os.path.dirname(os.path.abspath(__file__)).split("utils")[0]
    # get the experiment configuration
    uid = exp.db_name.split(os.sep)[1]
    data_base_path = f"{BASE_DIR}experiments{os.sep}{uid}{os.sep}"
    config_file = json.load(
        open(f"{data_base_path}client_{cli.name}-{population.name}.json")
    )

    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    filename = f"{BASE_DIR}{os.sep}{exp.db_name.split('database_server.db')[0]}{population.name.replace(' ', '')}.json".replace(
        "utils/", ""
    )

    # check if a Client_Execution object exists for client_id
    ce = Client_Execution.query.filter_by(client_id=cli.id).first()
    if ce:
        if not resume:
            ce.elapsed_time = 0
            ce.expected_duration_rounds = cli.days * 24
        first_run = False

    else:
        first_run = True

        # create a client execution object
        ce = Client_Execution(
            client_id=cli.id,
            elapsed_time=0,
            expected_duration_rounds=cli.days * 24,
            last_active_hour=-1,
            last_active_day=-1,
        )
        db.session.add(ce)
        db.session.commit()

    # add the network file if it is the first run (and the network is specified for the client)
    if first_run and cli.network_type is not None and cli.network_type != "":
        path = f"{cli.name}_network.csv"
        cl = YClientWeb(config_file, data_base_path, first_run=first_run, network=path)
    else:
        cl = YClientWeb(config_file, data_base_path, first_run=first_run)

    if resume:
        cl.days = int((ce.expected_duration_rounds - ce.elapsed_time) / 24)

    cl.read_agents()
    cl.add_feeds()

    if first_run and cli.network_type is not None and cli.network_type != "":
        cl.add_network()

    # check if filename exists
    if not os.path.exists(filename):
        cl.save_agents(filename)

    run_simulation(cl, cli.id, filename, exp)


def run_simulation(cl, cli_id, agent_file, exp):
    """
    Run the simulation
    """
    platform_type = exp.platform_type

    total_days = int(cl.days)
    daily_slots = int(cl.slots)

    for d1 in range(total_days):
        daily_active = {}
        tid, _, _ = cl.sim_clock.get_current_slot()

        for _ in range(daily_slots):
            tid, d, h = cl.sim_clock.get_current_slot()

            # get expected active users for this time slot (at least 1)
            expected_active_users = max(
                int(len(cl.agents.agents) * cl.hourly_activity[str(h)]), 1
            )

            page_agents = [p for p in cl.agents.agents if p.is_page]

            if platform_type == "microblogging":
                # pages post at least a news each slot of the day (7-22), more if they were selected randomly
                for page in page_agents:
                    if h < 7 or h > 22:
                        continue
                    page.select_action(
                        tid=tid,
                        actions=[],
                        max_length_thread_reading=cl.max_length_thread_reading,
                    )

                # check whether there are agents left
            if len(cl.agents.agents) == 0:
                break

            # get the daily activities of each agent
            # @todo: simplifiy once the daily_activity_level is always set on YReddit
            try:
                weights = [a.daily_activity_level for a in cl.agents.agents]
                # normalize weights to sum to 1
                weights = [w / sum(weights) for w in weights]
                # sample agents
                sagents = np.random.choice(
                    cl.agents.agents, size=expected_active_users, p=weights, replace=False
                )
            except Exception as e:
                sagents = np.random.choice(
                    cl.agents.agents, size=expected_active_users, replace=False
                )

            # available actions
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
                        # For forum experiments, all agents are regular users (no pages)
                        if platform_type == "forum" or g not in cl.pages:
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
            ce = Client_Execution.query.filter_by(client_id=cli_id).first()
            ce.elapsed_time += 1
            ce.last_active_hour = h
            ce.last_active_day = d
            db.session.commit()

        # evaluate follows (once per day, only for a random sample of daily active agents)
        if float(cl.config["agents"]["probability_of_daily_follow"]) > 0:
            da = [
                agent
                for agent in cl.agents.agents
                if agent.name in daily_active
                and (platform_type == "forum" or agent not in cl.pages)
                and random.random()
                < float(cl.config["agents"]["probability_of_daily_follow"])
            ]

            # Evaluating new friendship ties
            for agent in da:
                if platform_type == "forum" or agent not in cl.pages:
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
