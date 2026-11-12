import json
from dataclasses import replace
from pathlib import Path

import pytest

from zotero_file_explorer.core.models import Library, Record
from zotero_file_explorer.storage.index import Index, SearchFilter


@pytest.mark.parametrize("value", [[], {"bad": "text"}, {"[]": {}}, {'["a","b","c"]': {"state": "deleted"}}])
def test_invalid_overrides_preserved(tmp_path, value):
    path = tmp_path / "overrides.json"
    path.write_text(json.dumps(value), encoding="utf-8")
    index = Index(tmp_path)
    assert index.override_warning == "overrides_invalid"
    with pytest.raises(ValueError, match="overrides_invalid"):
        index.set_override("x", "y", "z", state="original")
    assert json.loads(path.read_text()) == value


def test_relocate_override_and_main_persist(index, tmp_path):
    relocated = tmp_path / "relocated 原件.pdf"
    relocated.write_bytes(b"fixture")
    index.set_override("server1", "user:0", "ATTACH01", path=str(relocated))
    index.reclassify([])
    reopened = Index(index.directory)
    reopened.reclassify([])
    row = reopened.search(SearchFilter())[0][0]
    primary = next(a for a in row["attachments"] if a["key"] == row["primary_key"])
    assert primary["path"] == str(relocated) and primary["status"] == "available"
    assert Path(primary["path"]).is_file()


def test_standalone_attachment_and_no_snapshot(tmp_path):
    file = tmp_path / "standalone.epub"
    file.write_bytes(b"fixture")
    attachment = Record("ATTACH01", "attachment", filename=file.name, title="Standalone", path=str(file))
    snapshot = replace(attachment, key="SNAPSHOT", filename="index.html", path="", content_type="text/html")
    index = Index(tmp_path / "index")
    library = Library("user:0", "personal", "users/0")
    index.replace_snapshot("server", [(library, {r.key: r for r in [attachment, snapshot]}, [], 1)], [])
    rows, count = index.search(SearchFilter())
    assert count == 1 and rows[0]["title"] == "Standalone"


def test_collection_and_library_keys_exact(index, library, records):
    group = Library("group:9", "Lab", "groups/9")
    other = {
        k: replace(r, collections=["COLLECT2"]) if r.kind != "attachment" else r for k, r in records.items()
    }
    index.replace_snapshot("server1", [(library, records, [], 1), (group, other, [], 1)], [])
    assert index.search(SearchFilter(library="user:0", collection="COLLECT1"))[1] == 1
    assert index.search(SearchFilter(library="group:9", collection="COLLECT1"))[1] == 0
    assert index.search(SearchFilter(library="group:9", collection="COLLECT2"))[1] == 1


def test_offline_file_error_recovers(index, records):
    path = Path(records["ATTACH01"].path)
    data = path.read_bytes()
    path.unlink()
    index.reclassify([])
    assert index.search(SearchFilter())[0][0]["status"] == "missing"
    path.write_bytes(data)
    index.reclassify([])
    assert index.search(SearchFilter())[0][0]["status"] == "available"
