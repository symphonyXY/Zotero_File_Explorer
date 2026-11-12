from dataclasses import replace
from pathlib import Path

import pytest

from zotero_file_explorer.core.classification import FilterRule, classify
from zotero_file_explorer.core.models import Record, choose_primary, parse_record
from zotero_file_explorer.services.paths import fallback_path, file_url_to_path, valid_file_paths
from zotero_file_explorer.storage.config import ConfigStore, Settings
from zotero_file_explorer.storage.index import Index, SearchFilter


@pytest.mark.parametrize(
    "token",
    [
        "compare",
        "crop-compare",
        "mono",
        "dual",
        "mono-cut",
        "dual-cut",
        "LR_dual",
        "TB_dual",
        "single-compare",
    ],
)
@pytest.mark.parametrize("separator", [".", "-"])
def test_pdf2zh_products(token, separator):
    original = Record("ORIGIN01", "attachment", filename="Paper.pdf", link_mode="imported_file")
    translated = replace(original, key="TRANSL01", filename=f"Paper{separator}{token}.pdf")
    assert classify(translated, [original, translated])[0] == "translated"


def test_real_glover_names():
    stem = "Glover 等 - 2019 - A Tutorial on Formulating and Using QUBO Models"
    original = Record("MQ4LNIWG", "attachment", filename=stem + ".pdf")
    translated = Record("LVA27WQM", "attachment", filename="b26624c7c4-" + stem + ".compare.pdf")
    assert classify(original, [original, translated])[0] == "original"
    assert classify(translated, [original, translated])[0] == "translated"


@pytest.mark.parametrize(
    "filename",
    [
        "Dual methods.pdf",
        "A mono study.pdf",
        "deadbeefaa-real.pdf",
        "Compare models.docx",
        "QUBO.epub",
        "paper.DOC",
        "paper.PDF",
    ],
)
def test_normal_titles_not_removed(filename):
    assert classify(Record("ORIGIN01", "attachment", filename=filename), [])[0] == "original"


@pytest.mark.parametrize("filename", ["Paper-dual.pdf", "Paper-cut.pdf", "Paper-single-compare.pdf"])
def test_ambiguous_legacy_needs_review(filename):
    assert classify(Record("ATTACH01", "attachment", filename=filename), [])[0] == "review"


def test_rule_manual_precedence():
    item = Record("ATTACH01", "attachment", filename="paper.compare.pdf")
    rules = [{"name": "Keep", "pattern": "*.compare.pdf", "state": "original"}]
    assert classify(item, [], rules)[0] == "original"
    assert classify(item, [], rules, "translated") == ("translated", "manual")
    assert classify(item, [], [{**rules[0], "enabled": False}])[0] == "translated"
    with pytest.raises(ValueError):
        FilterRule("bad", "x", "deleted").validate()


@pytest.mark.parametrize(
    "filename,mode", [("paper.html", "imported_url"), ("paper.pdf", "linked_url"), ("note.txt", "")]
)
def test_excluded_types(filename, mode):
    assert classify(Record("ATTACH01", "attachment", filename=filename, link_mode=mode), [])[0] == "excluded"


def test_parser_metadata():
    record = parse_record(
        {
            "key": "PAPER001",
            "version": 8,
            "data": {
                "itemType": "journalArticle",
                "title": "中文",
                "date": "2019-01-03",
                "creators": [{"firstName": "Fred", "lastName": "Glover"}, {"name": "Institute"}],
                "tags": [{"tag": "QUBO"}],
            },
        }
    )
    assert (record.authors, record.year, record.version, record.tags) == (
        "Fred Glover; Institute",
        "2019",
        8,
        ["QUBO"],
    )
    with pytest.raises(ValueError):
        parse_record({"key": "../a", "data": {}})


def test_file_url_unicode(tmp_path):
    path = tmp_path / "中文 #100%.pdf"
    path.write_bytes(b"test")
    assert Path(file_url_to_path(path.as_uri())) == path
    assert valid_file_paths([str(path), str(path), str(tmp_path / "missing.pdf")]) == [str(path)]
    for invalid in ["https://example.com/x.pdf", "file:///C:/a.pdf?x=1", "file:///C:/a.pdf%00"]:
        with pytest.raises(ValueError):
            file_url_to_path(invalid)


def test_metadata_paths(tmp_path):
    rec = Record("ATTACH01", "attachment", filename="test.pdf", path="storage:test.pdf")
    assert fallback_path(rec, str(tmp_path), "") == str(tmp_path / "storage/ATTACH01/test.pdf")
    assert fallback_path(replace(rec, path="storage:../escape.pdf"), str(tmp_path), "") == ""
    assert fallback_path(replace(rec, path="attachments:../escape.pdf"), "", str(tmp_path)) == ""
    assert fallback_path(replace(rec, path="attachments:中文/test.pdf"), "", str(tmp_path)) == str(
        tmp_path / "中文/test.pdf"
    )


def test_primary_stable():
    attachments = [
        {"key": k, "filename": filename, "state": state}
        for k, filename, state in [
            ("B", "b.pdf", "original"),
            ("A", "a.pdf", "original"),
            ("C", "a.docx", "original"),
            ("D", "translation.pdf", "translated"),
        ]
    ]
    assert choose_primary(attachments)["key"] == "A"
    assert choose_primary(list(reversed(attachments)))["key"] == "A"
    assert choose_primary(attachments, "C")["key"] == "C"
    assert choose_primary(attachments, "D")["key"] == "A"


@pytest.mark.parametrize(
    "text,expected",
    [
        ("glover 中文", 1),
        ("2019 QUBO", 1),
        ("10.1/TEST", 1),
        ("supplement", 1),
        ("Ising", 1),
        ("compare", 0),
        ("no match", 0),
    ],
)
def test_search(index, text, expected):
    assert index.search(SearchFilter(text=text))[1] == expected


def test_combined_filters(index):
    assert (
        index.search(
            SearchFilter(
                library="user:0",
                collection="COLLECT1",
                file_type=".docx",
                year="2019",
                tag="Ising",
                available=True,
            )
        )[1]
        == 1
    )
    assert index.search(SearchFilter(collection="__unfiled__"))[1] == 0
    assert index.search(SearchFilter(mode="translated"))[1] == 1
    assert index.search(SearchFilter(mode="errors"))[1] == 1


def test_overrides_survive_sync_rebuild(index, library, records):
    index.set_override("server1", library.id, "PAPER001", primary="ATTACH02")
    index.set_override("server1", library.id, "ATTACH03", state="original")
    index.replace_snapshot("server1", [(library, records, [], 3)], [])
    row = index.search(SearchFilter())[0][0]
    assert row["primary_key"] == "ATTACH02"
    assert next(a for a in row["attachments"] if a["key"] == "ATTACH03")["state"] == "original"
    index.rebuild()
    reopened = Index(index.directory)
    assert reopened.override("server1", library.id, "PAPER001")["primary"] == "ATTACH02"


def test_missing_file_preserved(index, records):
    Path(records["ATTACH01"].path).unlink()
    index.reclassify([])
    row = index.search(SearchFilter())[0][0]
    assert row["status"] == "missing"
    assert valid_file_paths([records["ATTACH01"].path]) == []


def test_corrupt_index_safe_recovery(tmp_path):
    (tmp_path / "index.sqlite3").write_bytes(b"broken SQLite")
    index = Index(tmp_path)
    assert index.recovery == "index_recovered"
    assert list(tmp_path.glob("*.corrupt-*"))
    assert index.search(SearchFilter())[1] == 0


def test_settings_roundtrip(tmp_path):
    store = ConfigStore(tmp_path)
    settings = Settings(language="en", poll_seconds=30)
    store.save(settings)
    assert store.load() == settings
    store.path.write_text("broken", encoding="utf-8")
    assert store.load() == Settings()
    store.save(settings)
    assert list(tmp_path.glob("*.invalid-*.json"))


def test_title_and_filename_separate(records, index):
    records["ATTACH01"].title = "Custom display title"
    index.reclassify([])
    assert index.search(SearchFilter(text="中文 paper"))[1] == 1
