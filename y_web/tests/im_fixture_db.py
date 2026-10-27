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


def enrich_db(path, info, seed=11):
    """Add what the analytics need on top of ``build_random_db``: topics, hashtags, mentions, reactions,
    toxicity and sentiment annotations, opinions, stress/reward and one forward. Returns the expected counts."""
    from y_web.src.im.engine import im_modules

    models = im_modules()[0]
    from sqlalchemy.orm import Session

    from yinstantmessaging.server.db.database import make_engine_from_url

    rng = random.Random(seed)
    engine = make_engine_from_url(f"sqlite:///{path}")
    acc, msgs, rounds = info["accounts"], info["messages"], info["rounds"]
    expected = {}
    with Session(engine) as s:
        round_of = {m.id: m.round_id for m in s.query(models.Message)}
        topics = [f"t{i}" for i in range(4)]
        for t in topics:
            s.add(models.Topic(id=t, label=f"topic {t}"))
        s.add(models.Hashtag(id=1, hashtag="alpha"))
        s.add(models.Hashtag(id=2, hashtag="beta"))
        s.flush()
        n_topics = n_tags = n_mentions = n_react = n_pos = n_neg = 0
        for mid in msgs:
            if rng.random() < 0.5:
                s.add(models.MessageTopic(message_id=mid, topic_id=rng.choice(topics), source="intended"))
                n_topics += 1
            if rng.random() < 0.2:
                s.add(models.MessageHashtag(message_id=mid, hashtag_id=rng.choice([1, 2])))
                n_tags += 1
            if rng.random() < 0.2:
                target = rng.choice(acc)
                s.add(models.Mention(message_id=mid, mentioned_account_id=target, username=target))
                n_mentions += 1
        seen = set()
        for _ in range(150):
            mid, a = rng.choice(msgs), rng.choice(acc)
            emoji = rng.choice(["👍", "❤", "👎", "😡", "🔥"])
            if (a, mid) in seen:
                continue
            seen.add((a, mid))
            s.add(models.Reaction(account_id=a, message_id=mid, emoji=emoji, round_id=round_of[mid]))
            n_react += 1
            if emoji in ("👎", "😡"):
                n_neg += 1
            else:
                n_pos += 1
        s.add(models.AnnotationMethod(method_ref="toxicity_detoxify_original:1:aaaa", method_id="toxicity_detoxify_original",
                                      version="1", params_hash="aaaa", params={}))
        s.add(models.AnnotationMethod(method_ref="sentiment_vader:1:bbbb", method_id="sentiment_vader", version="1",
                                      params_hash="bbbb", params={}))
        s.flush()
        n_tox = n_sent = 0
        for mid in msgs:
            if rng.random() < 0.6:
                s.add(models.Annotation(message_id=mid, method_ref="toxicity_detoxify_original:1:aaaa", status="ok",
                                        value={"toxicity": rng.random(), "severe_toxicity": 0.0, "identity_attack": 0.1,
                                               "insult": 0.2, "profanity": 0.0, "threat": 0.0, "sexually_explicit": 0.0,
                                               "flirtation": 0.0}))
                n_tox += 1
            if rng.random() < 0.6:
                status = "ok" if rng.random() < 0.9 else "error"
                s.add(models.Annotation(message_id=mid, method_ref="sentiment_vader:1:bbbb", status=status,
                                        value={"neg": 0.1, "neu": 0.6, "pos": 0.3, "compound": 0.4} if status == "ok" else None))
                n_sent += status == "ok"
        n_op = 0
        for a in acc[:5]:
            for t in topics[:3]:
                for r in (1, rounds // 2, rounds):
                    s.add(models.AgentOpinion(account_id=a, topic_id=t, value=rng.random(), round_id=r,
                                              cause_message_id=None))
                    n_op += 1
        n_sr = 0
        for i, a in enumerate(acc):
            for r in (1, rounds):
                s.add(models.StressReward(id=f"sr-{i}-{r}-s", uid=a, variable="stress", value=rng.random(),
                                          type="aggregate", action=None, tid=r))
                s.add(models.StressReward(id=f"sr-{i}-{r}-r", uid=a, variable="reward", value=rng.random(),
                                          type="aggregate", action=None, tid=r))
                n_sr += 2
        s.commit()
        expected.update(post=len(msgs), user_mgmt=len(acc), rounds=rounds, reactions=n_react, reactions_positive=n_pos,
                        reactions_negative=n_neg, mentions=n_mentions, post_topics=n_topics, post_hashtags=n_tags,
                        post_toxicity=n_tox, post_sentiment=n_sent, agent_opinion=n_op, stress_reward=n_sr)
    engine.dispose()
    return expected
