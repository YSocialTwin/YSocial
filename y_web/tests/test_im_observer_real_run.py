"""The observer reads the database of a real IM run, live and after it: zero divergence from IM (Phase 7 gate)."""

import datetime as dt
import hashlib
import random
from pathlib import Path

import pytest

from y_web.tests.test_im_client_creation import (  # noqa: F401
    IM_REPO,
    _post,
    _run_client,
    _seed,
    _start_server,
    env,
)


@pytest.mark.external_repo
@pytest.mark.integration
def test_reader_on_a_real_one_day_run_live_and_after_it(app, env, monkeypatch, tmp_path):
    if not (IM_REPO / "run_server.py").is_file():
        pytest.skip("YInstantMessaging is not installed")
    from y_web.src.hpc import server as hs
    from y_web.src.im import engine
    from y_web.src.im.reader import Reader, Viewpoint, latest_round, status

    with app.app_context():
        exp, pop = _seed(app, env)
        _post(app, env, exp, pop, days="1")
        folder = Path(env.im._experiment_folder(exp))
        db_file = folder / "database_server.db"
        _start_server(hs, exp, folder, monkeypatch, tmp_path)
        try:
            # live: the server owns the WAL database while we read it
            with engine.open_reader(str(db_file)) as session:
                assert status(session)["round"] >= 0
            assert _run_client(str(folder), "cl", timeout=150) == 0
            with engine.open_reader(str(db_file)) as session:
                live_latest = latest_round(session)
                assert live_latest >= 1
        finally:
            hs.stop_hpc_server(exp.idexp)

        before = hashlib.sha256(db_file.read_bytes()).hexdigest()
        from yinstantmessaging.server.db.repository import Repository
        from yinstantmessaging.server.services.feed import FeedService
        from yinstantmessaging.server.services.messages import RoundContext

        models = engine.im_modules()[0]
        feed = FeedService(max_items=50, window_minutes=100_000, visibility_lag_ticks=0)
        rng = random.Random(1)
        with engine.open_reader(str(db_file)) as session:
            latest = latest_round(session)
            accounts = [a.id for a in session.query(models.Account)]
            chats = [c.id for c in session.query(models.Chat)]
            messages = session.query(models.Message).count()
            assert accounts and chats and messages > 0, "the echo run produced no conversation"
            repo = Repository(session)
            tpr = 1  # tick values of a real run are small; the largest tick is used as the round's end
            max_tick = session.query(models.Message.tick).order_by(models.Message.tick.desc()).limit(1).scalar() or 0
            compared = 0
            for _ in range(120):
                account, chat = rng.choice(accounts), rng.choice(chats)
                rnd = rng.randint(1, latest)
                ctx = RoundContext(rnd, (rnd - 1) // 24 + 1, (rnd - 1) % 24 + 1, max_tick, max_tick + 1, dt.date(2026, 1, 1))
                theirs = feed.history(session, repo, account, ctx, chat, limit=10_000)
                rd = Reader(session, Viewpoint("account", account, rnd))
                ids, cursor = [], None
                while True:
                    page = rd.history(chat, before=cursor, limit=25)
                    if page is None:
                        ids = None
                        break
                    ids += [i["id"] for i in page["items"]]
                    cursor = page["next_before"]
                    if cursor is None:
                        break
                if theirs == "not_visible":
                    assert ids is None
                else:
                    assert ids == [i["message_id"] for i in theirs["items"]], (account, chat, rnd)
                    compared += 1
            assert compared > 0
            Reader(session, Viewpoint("overview", None, latest)).chat_list()
        assert hashlib.sha256(db_file.read_bytes()).hexdigest() == before
