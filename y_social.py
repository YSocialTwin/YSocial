from argparse import ArgumentParser

from y_web import create_app, db


def start_app(db_type="sqlite", debug=False, host="localhost", port=8080):
    import nltk

    nltk.download("vader_lexicon")

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

    args = parser.parse_args()

    start_app(db_type=args.db, debug=args.debug, host=args.host, port=args.port)
