from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

SUPPORTED = {".pdf", ".doc", ".docx", ".epub"}


class AttachmentState(StrEnum):
    ORIGINAL = "original"
    TRANSLATED = "translated"
    REVIEW = "review"
    EXCLUDED = "excluded"


def normalize(value: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", value).casefold() if not unicodedata.combining(c))


@dataclass(frozen=True)
class Library:
    id: str
    name: str
    prefix: str


@dataclass
class Record:
    key: str
    kind: str
    parent: str = ""
    title: str = ""
    authors: str = ""
    year: str = ""
    doi: str = ""
    tags: list[str] = field(default_factory=list)
    collections: list[str] = field(default_factory=list)
    filename: str = ""
    path: str = ""
    path_error: str = ""
    link_mode: str = ""
    content_type: str = ""
    version: int = 0
    state: str = AttachmentState.EXCLUDED
    reason: str = ""


def parse_record(obj: dict[str, Any]) -> Record:
    data = obj.get("data", obj)
    key = str(data.get("key") or obj.get("key", ""))
    if not re.fullmatch(r"[A-Za-z0-9]{8}", key):
        raise ValueError("Invalid Zotero item key")
    creators = data.get("creators") or []
    authors = "; ".join(
        str(c.get("name") or " ".join(filter(None, [c.get("firstName"), c.get("lastName")])))
        for c in creators
        if isinstance(c, dict)
    )
    match = re.search(r"\b(\d{4})\b", str(data.get("date", "")))
    return Record(
        key=key,
        kind=str(data.get("itemType", "")),
        parent=str(data.get("parentItem") or ""),
        title=str(data.get("title", "")),
        authors=authors,
        year=match.group(1) if match else "",
        doi=str(data.get("DOI", "")),
        tags=[str(t["tag"]) for t in data.get("tags", []) if isinstance(t, dict) and "tag" in t],
        collections=[str(c) for c in data.get("collections", [])],
        filename=str(data.get("filename") or ""),
        path=str(data.get("path") or ""),
        link_mode=str(data.get("linkMode") or ""),
        content_type=str(data.get("contentType") or ""),
        version=int(data.get("version", obj.get("version", 0))),
    )


def choose_primary(attachments: list[dict], manual: str = "") -> dict | None:
    originals = [a for a in attachments if a["state"] == AttachmentState.ORIGINAL]
    return min(
        originals,
        key=lambda a: (
            a["key"] != manual,
            Path(a["filename"]).suffix.casefold() != ".pdf",
            normalize(a["filename"]),
            a["key"],
        ),
        default=None,
    )
