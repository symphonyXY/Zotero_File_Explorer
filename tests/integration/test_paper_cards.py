import hashlib
import json
import threading
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import pytest
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QDialog, QPlainTextEdit

from zotero_file_explorer.api.client import APIError
from zotero_file_explorer.app import Controller
from zotero_file_explorer.core.paper_cards import CARD_TAG, CardTarget, card_template
from zotero_file_explorer.services.paper_cards import MultipleCards, PaperCards, new_card
from zotero_file_explorer.storage.config import ConfigStore
from zotero_file_explorer.storage.index import Index, SearchFilter


@pytest.fixture
def endpoint(tmp_path):
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"original")
    paper = dict(key="PAPER001", itemType="journalArticle", title="Test paper", date="2024")
    original = dict(
        key="ATTACH01",
        parentItem="PAPER001",
        itemType="attachment",
        linkMode="imported_file",
        filename=pdf.name,
    )
    ordinary = {**original, "key": "OTHER001", "filename": "PaperCard.md", "tags": [], "title": "Paper Card"}
    db = SimpleNamespace(
        items={i["key"]: i for i in (paper, original, ordinary)},
        version=1,
        partial=False,
        denied=False,
        edit_mid_upload=False,
        ticket=None,
        server_id="server1",
        paths={"ATTACH01": pdf, "OTHER001": tmp_path / "ordinary.md"},
    )
    db.paths["OTHER001"].write_text("personal notes", encoding="utf8")

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def send(self, data, status=200):
            self.send_response(status)
            self.send_header("Zotero-Server-ID", db.server_id)
            self.send_header("Last-Modified-Version", str(db.version))
            self.send_header("Zotero-API-Version", "3")
            self.send_header("X-Zotero-Version", "10.0.8")
            self.end_headers()
            self.wfile.write(data if isinstance(data, bytes) else json.dumps(data).encode())

        def do_GET(self):
            href = urlsplit(self.path)
            path = href.path.rsplit("/", 1)[-1]
            if self.headers.get("Zotero-Server-ID", db.server_id) != db.server_id:
                return self.send({}, 412)
            if path == "children":
                values = [i for i in db.items.values() if i.get("parentItem") == href.path.split("/")[-2]]
            elif path == "items":
                if parse_qs(href.query).get("format") == ["versions"]:
                    return self.send({k: db.version for k in db.items})
                values = list(db.items.values())
            elif path == "url":
                key = href.path.split("/")[-4]
                return self.send(db.paths[key].as_uri().encode())
            elif path in db.items:
                return self.send({"data": db.items[path]})
            elif path in {"collections", "groups", ""}:
                return self.send([])
            else:
                return self.send({}, 404)
            return self.send([{"key": i["key"], "version": db.version, "data": i} for i in values])

        def do_POST(self):
            body = self.rfile.read(int(self.headers["Content-Length"]))
            path = urlsplit(self.path).path
            if path.endswith("/authorize"):
                return self.send({"key": "test", "remember": True}, 403 if db.denied else 200)
            if path.endswith("/uploads/ticket"):
                db.ticket = body
                if db.edit_mid_upload:
                    db.paths[db.card].write_text("external editor", encoding="utf8")
                return self.send(b"", 201)
            if self.headers.get("Zotero-API-Key") != "test":
                return self.send({}, 401)
            if path.endswith("/items"):
                if self.headers["If-Unmodified-Since-Version"] != str(db.version):
                    return self.send({}, 412)
                (item,) = json.loads(body)
                assert item["version"] == 0 and item["key"] not in db.items
                db.card = item["key"]
                db.items[db.card] = item
                db.paths[db.card] = tmp_path / db.card / item["filename"]
                db.paths[db.card].parent.mkdir()
                db.version += 1
                return self.send({"successful": {"0": {"data": item}}})
            key = path.split("/")[-2]
            file = db.paths[key]
            if file.exists():
                if self.headers.get("If-Match") != hashlib.md5(file.read_bytes()).hexdigest():
                    return self.send({}, 412)
            elif self.headers.get("If-None-Match") != "*":
                return self.send({}, 412)
            if b"upload=" in body:
                if db.partial:
                    db.partial = False
                    return self.send({}, 503)
                file.write_bytes(db.ticket)
                db.version += 1
                return self.send(b"", 204)
            return self.send(
                dict(
                    uploadKey="ticket",
                    url=db.url + "local/uploads/ticket",
                    prefix="",
                    suffix="",
                    contentType="text/markdown",
                )
            )

        def do_PATCH(self):
            item = db.items[urlsplit(self.path).path.split("/")[-1]]
            if self.headers["If-Unmodified-Since-Version"] != str(item["version"]):
                return self.send({}, 412)
            item.update(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
            db.version += 1
            item["version"] = db.version
            self.send(b"", 204)

    http = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    db.url = f"http://127.0.0.1:{http.server_port}/api/"
    thread = threading.Thread(target=http.serve_forever, daemon=True)
    thread.start()
    yield db
    http.shutdown()
    http.server_close()
    thread.join()


def test_service_retries_and_conflicts(endpoint):
    service = PaperCards(endpoint.url, "server1")
    target = CardTarget("server1", "user:0", "PAPER001")
    first = new_card(card_template())
    endpoint.partial = True
    with pytest.raises(APIError):
        service.save(target, first)
    saved = service.save(target, first)
    assert saved.attachment == first.attachment and saved.text == first.text and not saved.creating
    with pytest.raises(APIError, match="card_changed"):
        service.save(target, new_card("duplicate"))
    second = service.save(target, replace(saved, text="# 新结果"))
    assert second == service.read(target, first.attachment)
    assert service.save(target, replace(saved, text=second.text)) == second  # lost successful response
    with pytest.raises(APIError, match="card_conflict"):
        service.save(target, replace(saved, text="stale"))
    endpoint.edit_mid_upload = True
    with pytest.raises(APIError, match="card_conflict"):
        service.save(target, replace(second, text="edited during authorization"))
    assert endpoint.paths[second.attachment].read_text() == "external editor"
    assert endpoint.paths["OTHER001"].read_text() == "personal notes"
    with pytest.raises(APIError, match="card_personal"):
        service.save(replace(target, library="group:7"), first)
    endpoint.server_id = "different"
    with pytest.raises(APIError, match="instance_changed"):
        service.read(target, first.attachment)


def test_card_gui_create_restore_merge_and_recall(qapp, qtbot, index, endpoint):
    config = ConfigStore(index.directory)
    settings = config.load()
    settings.api_url = endpoint.url
    config.save(settings)
    ctrl = Controller(qapp, config, start_sync=False, register_hotkey=False)
    qtbot.addWidget(ctrl.main)
    qtbot.addWidget(ctrl.quick)
    ctrl.show_main()
    main = ctrl.main

    def idle():
        qtbot.waitUntil(lambda: not ctrl.tasks and main.results_ready)

    def enter():
        main.view.setCurrentIndex(main.view.model_data.index(0, 0))
        main.card_button.click()
        dialog = ctrl.card_dialog
        qtbot.waitUntil(lambda: not dialog.busy)
        return dialog

    try:
        idle()
        endpoint.denied = True
        d = enter()
        assert d.dirty and d.draft.creating and "保存失败" in d.status.text()
        d.editor.setPlainText("# 恢复草稿\n\n中文")
        d.reject()
        qtbot.waitUntil(lambda: ctrl.card_dialog is None)
        endpoint.denied = False
        d = enter()
        assert d.editor.toPlainText().endswith("中文") and d.dirty
        d.save.click()
        idle()
        assert not d.dirty and d.mode.currentIndex() == 1 and "云端同步状态未知" in d.status.text()
        assert endpoint.items[endpoint.card]["tags"] == [{"tag": CARD_TAG}]
        assert index.search(SearchFilter(card="with"))[1] == 1
        assert index.search(SearchFilter(card="without"))[1] == 0
        main.view.setCurrentIndex(main.view.model_data.index(0, 0))
        assert [a["path"] for a in main.view.selected_attachments(True)] == [str(endpoint.paths["ATTACH01"])]
        d.mode.setCurrentIndex(2)
        assert not d.answer.isVisible()
        d.reveal.click()
        assert d.answer.isVisible() and "中文" in d.answer.toPlainText()
        d.reveal.click()
        assert not d.answer.isVisible()
        d.mode.setCurrentIndex(1)
        d.editor.setPlainText("local edit")
        endpoint.paths[endpoint.card].write_text("other revision", encoding="utf8")
        d.save.click()
        qtbot.waitUntil(lambda: not d.busy)
        assert d.merge.isVisible() and d.editor.toPlainText() == "local edit"

        def merge():
            modal = QApplication.activeModalWidget()
            if modal is d or not isinstance(modal, QDialog):
                QTimer.singleShot(20, merge)
                return
            source, edit = modal.findChildren(QPlainTextEdit)
            assert source.toPlainText() == "other revision"
            edit.setPlainText("merged")
            modal.accept()

        QTimer.singleShot(20, merge)
        d.merge.click()
        qtbot.waitUntil(lambda: d.editor.toPlainText() == "merged")
        d.save.click()
        idle()
        assert endpoint.paths[endpoint.card].read_text() == "merged"
        d.reject()
        qtbot.waitUntil(lambda: ctrl.card_dialog is None)
        d = enter()
        assert d.mode.currentIndex() == 0 and d.preview.toPlainText() == "merged"
        assert not list((index.directory / "paper-card-drafts").glob("*.json"))
        assert Path(endpoint.paths["ATTACH01"]).read_bytes() == b"original"
    finally:
        ctrl.quitting = True
        ctrl.poll.stop()
        ctrl.tray.hide()
        ctrl.pool.waitForDone(10000)
        ctrl.card_drafts.executor.shutdown()
        qapp.processEvents()
        qapp.removeNativeEventFilter(ctrl.hotkey)


def test_marker_fallback_survives_freeform_edit(endpoint):
    target = CardTarget("server1", "user:0", "PAPER001")
    service = PaperCards(endpoint.url, target.instance)
    key = "OTHER001"
    endpoint.items[key].update(tags=[{"tag": "keep"}], version=1)
    endpoint.paths[key].write_text(card_template(), encoding="utf8")
    assert service.candidates(target)[0].card_marker
    saved = service.save(target, replace(service.read(target, key), text="Freeform without front matter"))
    assert endpoint.items[key]["tags"] == [{"tag": "keep"}, {"tag": CARD_TAG}]
    assert service.read(target, key) == saved


def test_new_duplicate_requires_explicit_target(endpoint):
    target = CardTarget("server1", "user:0", "PAPER001")
    service = PaperCards(endpoint.url, target.instance)
    first = service.save(target, new_card("original card"))
    endpoint.items["OTHER001"]["tags"] = [{"tag": CARD_TAG}]
    edit = replace(first, text="selected card only")
    with pytest.raises(MultipleCards) as conflict:
        service.save(target, edit)
    assert endpoint.paths[first.attachment].read_text() == first.text
    assert service.save(target, edit, conflict.value.keys).text == edit.text
    assert endpoint.paths["OTHER001"].read_text() == "personal notes"


def test_old_cache_opens_offline_until_next_projection(index):
    with index.connection() as db:
        db.execute("DROP TABLE document_cards")
    reopened = Index(index.directory)
    rows, count = reopened.search(SearchFilter())
    assert count == 1 and rows[0]["card_state"] == "card_unknown"
    assert reopened.search(SearchFilter(card="without"))[1] == 0
    reopened.reclassify([])
    assert reopened.search(SearchFilter(card="without"))[1] == 1
