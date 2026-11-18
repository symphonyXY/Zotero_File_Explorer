import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs
from uuid import uuid4

import pytest

from zotero_file_explorer.api.client import APIError

spec = importlib.util.spec_from_file_location(
    "probe_paper_cards", Path(__file__).resolve().parents[2] / "scripts/probe_paper_cards.py"
)
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


@pytest.fixture
def transfer():
    instance = probe.Probe.__new__(probe.Probe)
    instance.api = SimpleNamespace(base_url="http://127.0.0.1:23119/api/")
    return instance


def test_upload_conditions_and_exact_utf8_bytes(transfer):
    _, card, first, final = probe.fixture(uuid4())
    calls = []
    key = "testTicket"
    path = f"local/uploads/{key}"

    def post(target, data, content_type, **kwargs):
        calls.append((target, data, content_type, kwargs))
        if len(calls) == 1:
            return json.dumps(dict(uploadKey=key, url=transfer.api.base_url + path, prefix="", suffix="",
                                   contentType="text/markdown")).encode()
        return b""

    transfer.post = post
    transfer.upload(card, final, first)
    start, upload, finish = calls
    assert start[0] == finish[0] == f"users/0/items/{card['key']}/file"
    assert start[3]["headers"] == finish[3]["headers"] == {"If-Match": hashlib.md5(first).hexdigest()}
    assert parse_qs(start[1])[b"md5"] == [hashlib.md5(final).hexdigest().encode()]
    assert upload == (path, final, "text/markdown", {"auth": False, "expected": 201})
    assert parse_qs(finish[1]) == {b"upload": [key.encode()]}


@pytest.mark.parametrize("target", ["https://example.invalid/", "http://127.0.0.1:23120/api/"])
def test_foreign_upload_address_stops_before_sending_bytes(transfer, target):
    _, card, first, _ = probe.fixture(uuid4())
    calls = []

    def post(path, data, content_type, **kwargs):
        calls.append(kwargs["headers"])
        plan = dict(uploadKey="xyz", url=target + "local/uploads/xyz", prefix="", suffix="")
        return json.dumps(plan).encode()

    transfer.post = post
    with pytest.raises(ValueError, match="destination"):
        transfer.upload(card, first, None)
    assert calls == [{"If-None-Match": "*"}]


def test_verify_only_and_retry_with_existing_final(transfer, monkeypatch):
    run = uuid4()
    parent, card, first, final = probe.fixture(run)
    data = {**card, "tags": [{"tag": probe.TAG}]}
    children = [{"key": card["key"], "data": data}]
    transfer.api.list_all = lambda path: (children, 1)
    transfer.api.get = lambda path: SimpleNamespace(json=lambda: {"data": (
        data if path.endswith(card["key"]) else {**parent, "tags": [{"tag": probe.TAG}]}
    )})
    monkeypatch.setattr(transfer, "read", lambda _: final)
    calls = []

    def stale(_, body, base, *, expect_stale):
        calls.append((body, base, expect_stale))
        raise APIError(412, "stale")

    monkeypatch.setattr(transfer, "upload", stale)
    transfer.run(run, write=False)
    assert not calls
    transfer.run(run, write=True)
    assert calls == [(first, first, True)]
    children.append(children[0])
    with pytest.raises(ValueError, match="ambiguous"):
        transfer.run(run, write=True)
    children.pop()
    data["tags"] = []
    with pytest.raises(ValueError, match="identity"):
        transfer.run(run, write=True)


def test_unexpected_body_preserved(transfer, monkeypatch):
    run = uuid4()
    _, card, _, _ = probe.fixture(run)
    monkeypatch.setattr(transfer, "item", lambda *a, **kw: card)
    transfer.api.list_all = lambda path: ([{"key": card["key"], "data": {"tags": [{"tag": probe.TAG}]}}], 1)
    monkeypatch.setattr(transfer, "read", lambda _: b"user edited the test card")
    with pytest.raises(ValueError, match="preserved"):
        transfer.run(run, write=True)
