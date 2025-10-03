import os
from argparse import ArgumentParser

from y_web import create_app, db


def start_app(
    db_type="sqlite", debug=False, host="localhost", port=8080, llm_backend="ollama"
):
    import nltk
    import requests
    import sys

    nltk.download("vader_lexicon")

    # Parse and validate LLM backend
    llm_url = None
    if llm_backend == "ollama":
        llm_url = "http://127.0.0.1:11434/v1"
    elif llm_backend == "vllm":
        llm_url = "http://127.0.0.1:8000/v1"
    elif ":" in llm_backend:
        # Custom URL provided
        if not llm_backend.startswith("http"):
            llm_url = f"http://{llm_backend}/v1"
        else:
            llm_url = llm_backend if llm_backend.endswith("/v1") else f"{llm_backend}/v1"
    else:
        print(f"Error: Invalid LLM backend '{llm_backend}'")
        print("Valid options: 'ollama', 'vllm', or custom URL (host:port)")
        sys.exit(1)
    
    # Check if LLM server is reachable
    try:
        # Try to reach the models endpoint
        models_url = llm_url.replace("/v1", "/v1/models") if "/v1" in llm_url else f"{llm_url}/models"
        response = requests.get(models_url, timeout=5)
        if response.status_code not in [200, 404]:  # 404 is ok, means endpoint exists but no route
            print(f"Warning: LLM server at {llm_url} responded with status {response.status_code}")
    except requests.exceptions.RequestException as e:
        print(f"Error: Cannot reach LLM server at {llm_url}")
        print(f"Details: {e}")
        print("\nMake sure the LLM server is running before starting YSocial.")
        sys.exit(1)
    
    # Set the LLM backend and URL as environment variables for the app to use
    os.environ["LLM_BACKEND"] = llm_backend
    os.environ["LLM_URL"] = llm_url

    app = create_app(db_type=db_type)

    with app.app_context():
        from y_web.models import Exps

        exps = Exps.query.filter_by(status=1).all()
        for exp in exps:
            exp.status = 0
        db.session.commit()

    app.run(debug=debug, host=host, port=port)


if __name__ == "__main__":
    parser = ArgumentParser()

    parser.add_argument(
        "-x", "--host", default="localhost", help="host address to run the app on"
    )
    parser.add_argument("-y", "--port", default="8080", help="port to run the app on")
    parser.add_argument(
        "-d", "--debug", default=False, action="store_true", help="debug mode"
    )
    parser.add_argument(
        "-D",
        "--db",
        choices=["sqlite", "postgresql"],
        default="sqlite",
        help="Database type",
    )
    parser.add_argument(
        "-l",
        "--llm-backend",
        default="ollama",
        help="LLM backend to use: 'ollama' (default), 'vllm', or custom URL (host:port)",
    )

    args = parser.parse_args()

    start_app(
        db_type=args.db,
        debug=args.debug,
        host=args.host,
        port=args.port,
        llm_backend=args.llm_backend,
    )
