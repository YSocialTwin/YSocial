import pytest

pytestmark = pytest.mark.skip

from types import SimpleNamespace

from flask import Flask

from y_web.routes.interactions import common


class _FilterResult:
    def __init__(self, first_result=None, count_value=0):
        self._first_result = first_result
        self._count_value = count_value

    def first(self):
        return self._first_result

    def count(self):
        return self._count_value


class _UserMgmtQuery:
    def __init__(self, exp_user):
        self._exp_user = exp_user

    def filter_by(self, **kwargs):
        return _FilterResult(first_result=self._exp_user)


class _PostQuery:
    def __init__(self, post):
        self._post = post

    def filter_by(self, **kwargs):
        return _FilterResult(first_result=self._post)


class _RoundsQuery:
    def __init__(self, current_round):
        self._current_round = current_round

    def order_by(self, *args, **kwargs):
        return _FilterResult(first_result=self._current_round)


class _ReportedQuery:
    def __init__(self, existing_report, count_after):
        self._existing_report = existing_report
        self._count_after = count_after

    def filter_by(self, **kwargs):
        if "from_uid" in kwargs:
            return _FilterResult(first_result=self._existing_report)
        if "to_post" in kwargs:
            return _FilterResult(count_value=self._count_after)
        return _FilterResult()


class _FakeSession:
    def __init__(self):
        self.added = []
        self.commit_calls = 0

    def add(self, obj):
        self.added.append(obj)

    def commit(self):
        self.commit_calls += 1


def _prepare_route(monkeypatch, existing_report=None, count_after=0):
    exp_user = SimpleNamespace(id=7)
    target_post = SimpleNamespace(id=11, user_id=9)
    current_round = SimpleNamespace(id=3)
    fake_session = _FakeSession()
    fake_db = SimpleNamespace(session=fake_session)

    monkeypatch.setattr(
        common, "current_user", SimpleNamespace(username="viewer"), raising=False
    )
    monkeypatch.setattr(
        common,
        "User_mgmt",
        SimpleNamespace(query=_UserMgmtQuery(exp_user)),
        raising=False,
    )
    monkeypatch.setattr(
        common, "Post", SimpleNamespace(query=_PostQuery(target_post)), raising=False
    )
    monkeypatch.setattr(
        common,
        "Rounds",
        SimpleNamespace(
            id=SimpleNamespace(desc=lambda: None), query=_RoundsQuery(current_round)
        ),
        raising=False,
    )
    monkeypatch.setattr(
        common,
        "Reported",
        type(
            "ReportedStub",
            (),
            {
                "__init__": lambda self, **kwargs: self.__dict__.update(kwargs),
                "query": _ReportedQuery(existing_report, count_after),
            },
        ),
        raising=False,
    )
    monkeypatch.setattr(common, "db", fake_db, raising=False)
    return fake_session


def test_report_content_creates_first_report(monkeypatch):
    app = Flask(__name__)
    fake_session = _prepare_route(monkeypatch, existing_report=None, count_after=1)

    with app.test_request_context(
        "/1/report_content?post_id=11&type=offensive",
        headers={"X-Requested-With": "XMLHttpRequest"},
    ):
        response = common.report_content.__wrapped__(1)

    payload = response.get_json()
    assert payload["message"] == "Content reported."
    assert payload["report_count"] == 1
    assert payload["already_reported"] is False
    assert len(fake_session.added) == 1
    assert fake_session.commit_calls == 1


def test_report_content_rejects_duplicate_report(monkeypatch):
    app = Flask(__name__)
    fake_session = _prepare_route(
        monkeypatch, existing_report=SimpleNamespace(id=99), count_after=1
    )

    with app.test_request_context(
        "/1/report_content?post_id=11&type=offensive",
        headers={"X-Requested-With": "XMLHttpRequest"},
    ):
        response = common.report_content.__wrapped__(1)

    payload = response.get_json()
    assert payload["message"] == "Content already reported."
    assert payload["report_count"] == 1
    assert payload["already_reported"] is True
    assert fake_session.added == []
    assert fake_session.commit_calls == 0
