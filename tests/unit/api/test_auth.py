from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from podcast_compactor.api.auth import make_require_token


def _client(token):
    app = FastAPI()

    @app.get("/x", dependencies=[Depends(make_require_token(token))])
    def x():
        return {"ok": True}

    return TestClient(app)


def test_rejects_missing_token():
    assert _client("secret").get("/x").status_code == 401


def test_rejects_wrong_token():
    r = _client("secret").get("/x", headers={"Authorization": "Bearer nope"})
    assert r.status_code == 401


def test_accepts_correct_token():
    r = _client("secret").get("/x", headers={"Authorization": "Bearer secret"})
    assert r.status_code == 200


def test_disabled_when_token_is_none():
    assert _client(None).get("/x").status_code == 200
