import pytest

from zotero_file_explorer.core.models import Library, Record
from zotero_file_explorer.storage.index import Index


@pytest.fixture
def library():
    return Library("user:0", "personal", "users/0")


@pytest.fixture
def records(tmp_path):
    pdf = tmp_path / "中文 paper.pdf"
    pdf.write_bytes(b"%PDF-1.4\nfixture\n%%EOF")
    doc = tmp_path / "supplement.docx"
    doc.write_bytes(b"fixture only")
    return {
        "PAPER001": Record(
            "PAPER001",
            "journalArticle",
            title="Quantum 中文 QUBO",
            authors="Glover",
            year="2019",
            doi="10.1/test",
            tags=["Ising"],
            collections=["COLLECT1"],
        ),
        "ATTACH01": Record(
            "ATTACH01",
            "attachment",
            parent="PAPER001",
            filename=pdf.name,
            path=str(pdf),
            link_mode="imported_file",
        ),
        "ATTACH02": Record(
            "ATTACH02",
            "attachment",
            parent="PAPER001",
            filename=doc.name,
            path=str(doc),
            link_mode="linked_file",
        ),
        "ATTACH03": Record(
            "ATTACH03",
            "attachment",
            parent="PAPER001",
            filename="中文 paper.compare.pdf",
            link_mode="imported_file",
        ),
    }


@pytest.fixture
def index(tmp_path, library, records):
    index = Index(tmp_path / "appdata")
    index.replace_snapshot(
        "server1", [(library, records, [{"key": "COLLECT1", "name": "电路", "parentCollection": ""}], 1)], []
    )
    return index
