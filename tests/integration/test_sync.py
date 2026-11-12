import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

import pytest

from zotero_file_explorer.api.client import APIError, InstanceChanged, LocalAPI
from zotero_file_explorer.services.sync import SyncService
from zotero_file_explorer.storage.config import Settings
from zotero_file_explorer.storage.index import Index, SearchFilter


@pytest.fixture
def server(tmp_path):
    file = tmp_path / "测试 paper.pdf"
    file.write_bytes(b"%PDF fixture")
    data = {
        "id": "test-instance",
        "version": 1,
        "groups": [{"id": 5, "data": {"name": "Lab"}}],
        "disabled": False,
        "requests": [],
        "file": file,
        "change_midway": False,
        "items": [
            {
                "key": "PAPER001",
                "version": 1,
                "data": {
                    "key": "PAPER001",
                    "itemType": "journalArticle",
                    "title": "Original",
                    "collections": ["COLLECT1"],
                },
            },
            {
                "key": "ATTACH01",
                "version": 1,
                "data": {
                    "key": "ATTACH01",
                    "itemType": "attachment",
                    "parentItem": "PAPER001",
                    "filename": file.name,
                    "linkMode": "linked_file",
                },
            },
        ],
    }

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            parsed = urlsplit(self.path)
            query = parse_qs(parsed.query)
            data["requests"].append((self.path, dict(self.headers)))
            headers = {"Zotero-API-Version": "3", "Last-Modified-Version": str(data["version"])}
            if data["id"]:
                headers["Zotero-Server-ID"] = data["id"]
            if data["disabled"]:
                self.send_error(403)
                return
            if self.headers.get("Zotero-Server-ID") and self.headers["Zotero-Server-ID"] != data["id"]:
                self.send_error(412)
                return
            if parsed.path == "/api/":
                body = "Nothing to see here."
            elif parsed.path.endswith("/groups"):
                body = data["groups"]
            elif parsed.path.endswith("/file/view/url"):
                body = file.as_uri()
            elif parsed.path.endswith("/collections"):
                body = [
                    {"data": {"key": "COLLECT1", "name": "Root", "parentCollection": False}},
                    {"data": {"key": "COLLECT2", "name": "Nested", "parentCollection": "COLLECT1"}},
                ]
            elif parsed.path.endswith("/items"):
                if query.get("format") == ["versions"]:
                    body = {i["key"]: i["version"] for i in data["items"]}
                else:
                    since = int(query.get("since", [0])[0])
                    body = [i for i in data["items"] if i["version"] > since]
                    start = int(query.get("start", [0])[0])
                    body = body[start : start + 100]
                    if data["change_midway"]:
                        data["version"] += 1
            else:
                self.send_error(404)
                return
            raw = (body if isinstance(body, str) else json.dumps(body)).encode()
            self.send_response(200)
            for key, value in headers.items():
                self.send_header(key, value)
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

    http = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=http.serve_forever, daemon=True)
    thread.start()
    yield data, f"http://127.0.0.1:{http.server_port}/api/"
    http.shutdown()
    http.server_close()
    thread.join()


def make_service(tmp_path, server):
    _, url = server
    return SyncService(Index(tmp_path / "cache"), Settings(api_url=url))


def test_online_groups_key_collision_offline(tmp_path, server):
    service = make_service(tmp_path, server)
    result = service.synchronize()
    assert result["libraries"] == 2
    rows, count = service.index.search(SearchFilter())
    assert count == 2 and rows[0]["key"] == rows[1]["key"]
    assert {r["library"] for r in rows} == {"user:0", "group:5"}
    assert rows[0]["attachments"][0]["path"] == str(server[0]["file"])
    reopened = Index(service.index.directory)
    assert reopened.search(SearchFilter(text="测试"))[1] == 2


def test_incremental_modify_delete_add_groups(tmp_path, server):
    data, _ = server
    service = make_service(tmp_path, server)
    service.synchronize()
    data["version"] = 2
    data["items"][0]["version"] = 2
    data["items"][0]["data"]["title"] = "Changed"
    data["items"].append(
        {
            "key": "ATTACH02",
            "version": 2,
            "data": {
                "key": "ATTACH02",
                "itemType": "attachment",
                "parentItem": "PAPER001",
                "filename": "supplement.pdf",
            },
        }
    )
    service.synchronize()
    assert service.index.search(SearchFilter(text="Changed"))[1] == 2
    assert any("since=1" in path for path, headers in data["requests"])
    data["version"] = 3
    data["items"] = data["items"][:1]
    data["groups"] = []
    service.synchronize()
    assert service.index.search(SearchFilter())[1] == 0
    assert len(service.index.libraries()) == 1


def test_instance_isolation_and_versions(tmp_path, server):
    data, _ = server
    service = make_service(tmp_path, server)
    service.synchronize()
    service.index.set_override("test-instance", "user:0", "ATTACH01", state="translated")
    data["id"] = "new-instance"
    data["version"] = 1
    data["requests"] = []
    service.synchronize()
    assert service.index.active_instance() == "new-instance"
    assert service.index.search(SearchFilter())[1] == 2
    assert not any("since=" in p for p, h in data["requests"])
    assert service.index.override("new-instance", "user:0", "ATTACH01") == {}


def test_failure_keeps_snapshot_and_recovery(tmp_path, server):
    data, _ = server
    service = make_service(tmp_path, server)
    service.synchronize()
    data["disabled"] = True
    with pytest.raises(APIError, match="api_disabled"):
        service.synchronize()
    assert service.index.search(SearchFilter())[1] == 2
    data["disabled"] = False
    service.synchronize()
    assert service.index.search(SearchFilter())[1] == 2


def test_atomic_consistency_fence(tmp_path, server):
    data, _ = server
    service = make_service(tmp_path, server)
    service.synchronize()
    data["change_midway"] = True
    with pytest.raises(APIError, match="library_changed_during_sync"):
        service.synchronize()
    assert service.index.search(SearchFilter())[1] == 2


def test_legacy_never_since(tmp_path, server):
    data, _ = server
    data["id"] = ""
    service = make_service(tmp_path, server)
    assert service.synchronize()["legacy"]
    data["items"][0]["data"]["title"] = "Locally changed without version bump"
    service.synchronize()
    assert service.index.search(SearchFilter(text="Locally changed"))[1] == 2
    assert not any("since=" in p for p, h in data["requests"])


def test_client_errors_and_instance_guard(server):
    data, url = server
    api = LocalAPI(url)
    api.probe()
    data["id"] = "another"
    with pytest.raises(InstanceChanged):
        api.libraries()
    with pytest.raises(APIError) as error:
        api.get("not-there")
    assert error.value.code == 412
    for bad in ["https://zotero.org/api/", "http://127.0.0.1:23119/notapi/", "http://evil/api/"]:
        with pytest.raises(ValueError):
            LocalAPI(bad)
