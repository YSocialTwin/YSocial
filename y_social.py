from y_web import app, db
import logging


def start_app(debug=False, host="localhost", port=8080):
    """
    Start the app

    :param debug: turn on debug mode
    :param port: the port to run the app on
    :param host: the host to run the app on
    """

    # Enable debug logging
    logging.basicConfig(level=logging.DEBUG)
    app.logger.setLevel(logging.DEBUG)

    import nltk

    nltk.download("vader_lexicon")

    # unload all experiments
    from y_web.models import Exps

    # select all loaded experiments
    exps = Exps.query.filter_by(status=1).all()
    # stop all the experiments
    for exp in exps:
        exp.status = 0
    db.session.commit()

    app.run(debug=debug, host=host, port=port)


if __name__ == "__main__":
    from argparse import ArgumentParser

    parser = ArgumentParser()

    parser.add_argument(
        "-x",
        "--host",
        default=f"localhost",
        help="host address to run the app on",
    )

    parser.add_argument(
        "-y",
        "--port",
        default=f"8080",
        help="port to run the app on",
    )

    parser.add_argument(
        "-d",
        "--debug",
        default=False,
        help="whether to run the app in debug mode",
    )

    args = parser.parse_args()

    start_app(debug=args.debug, host=args.host, port=args.port)
