"""Builds IM databases for read-model tests with IM's own models and Repository (no Ray, no LLM)."""

import random
from datetime import datetime
from pathlib import Path


def build_random_db(path, seed=7, accounts=8, chats=7, rounds=48, messages=220):
    """A populated IM database: public/private chats, channels with discussion groups, forums, bans,
    leaves, deletions, edits, reactions. Returns the lists of ids for the tests to sample from."""
    from y_web.src.im.engine import im_modules

    models, _vis, _views, schema_migrations = im_modules()
    from sqlalchemy import insert
    from sqlalchemy.orm import Session

    from yinstantmessaging.server.db.database import make_engine_from_url
    from yinstantmessaging.server.db.repository import Repository

    rng = random.Random(seed)
    engine = make_engine_from_url(f"sqlite:///{path}")
    schema_migrations.migrate(engine)
    acc_ids = [f"a{i}" for i in range(accounts)]
    chat_ids = [f"c-{i}" for i in range(chats)]
    msg_ids = []
    with Session(engine) as session:
        repo = Repository(session)
        for r in range(1, rounds + 1):
            repo.ensure_round(r, (r - 1) // 24 + 1, (r - 1) % 24 + 1)
        for i, a in enumerate(acc_ids):
            repo.add_account(a, f"user{i}", kind="agent" if i else "human",
                             status="active" if i != accounts - 1 else "churned")
        kinds = ["group", "channel", "supergroup", "private", "group", "channel", "supergroup"]
        for i, c in enumerate(chat_ids):
            kind = kinds[i % len(kinds)]
            repo.add_chat(
                c, kind, title=f"Chat {i}",
                visibility=rng.choice(["public", "private"]) if kind != "private" else "private",
                is_forum=(kind == "supergroup" and i % 2 == 0),
                created_round=1,
            )
            for a in acc_ids:
                if rng.random() < 0.65:
                    role = rng.choice(["owner", "admin", "member", "member", "subscriber", "restricted",
                                       "banned", "left"])
                    if role in ("owner", "admin", "subscriber", "restricted"):
                        perms = None
                    else:
                        perms = None
                    joined = rng.randint(1, rounds // 2)
                    left = rng.randint(joined + 1, rounds + 5) if (role == "left" or rng.random() < .15) else None
                    try:
                        with session.begin_nested():
                            repo.add_member(c, a, role, perms, joined_round=joined, left_round=left)
                    except Exception:
                        pass  # a role/permission pair IM refuses is simply not in the fixture
        session.commit()
        for n in range(messages):
            c = rng.choice(chat_ids)
            sender = rng.choice(acc_ids)
            rnd = rng.randint(1, rounds)
            mid = f"m{n:04d}"
            deleted = rng.randint(rnd, rounds + 3) if rng.random() < 0.12 else None
            reply = rng.choice(msg_ids) if msg_ids and rng.random() < 0.25 else None
            row = repo.add_message(
                mid, c, rnd, sender_account_id=sender, text=f"text {n}", tick=rng.randint(0, 3),
                sim_ts=datetime(2026, 1, (rnd - 1) // 24 + 1, (rnd - 1) % 24, rng.randint(0, 59)),
                deleted_round=deleted, reply_to_message_id=reply,
            )
            msg_ids.append(mid)
        session.commit()
    engine.dispose()
    return {"accounts": acc_ids, "chats": chat_ids, "messages": msg_ids, "rounds": rounds}
