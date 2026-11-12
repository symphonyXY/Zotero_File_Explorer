from __future__ import annotations

import json
import shlex
import sqlite3
import threading
import time
from contextlib import contextmanager
from dataclasses import asdict, dataclass, replace
from pathlib import Path

from ..core.classification import classify
from ..core.models import AttachmentState, Record, choose_primary, normalize
from ..services.paths import file_status
from .config import atomic_json


@dataclass
class SearchFilter:
    text: str = ""
    library: str = ""
    collection: str = ""
    file_type: str = ""
    year: str = ""
    tag: str = ""
    available: bool = False
    mode: str = "all"
    limit: int = 500
    offset: int = 0
    sort: str = "title"
    descending: bool = False


SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS libraries (
 instance TEXT, id TEXT, name TEXT, prefix TEXT, version INTEGER,
 PRIMARY KEY(instance,id));
CREATE TABLE IF NOT EXISTS items (
 instance TEXT, library TEXT, key TEXT, payload TEXT,
 PRIMARY KEY(instance,library,key));
CREATE TABLE IF NOT EXISTS collections (
 instance TEXT, library TEXT, key TEXT, name TEXT, parent TEXT,
 PRIMARY KEY(instance,library,key));
CREATE TABLE IF NOT EXISTS documents (
 instance TEXT, library TEXT, key TEXT, title TEXT, authors TEXT, year TEXT,
 doi TEXT, tags TEXT, collections TEXT, search TEXT, attachments TEXT,
 filename TEXT, type TEXT, size INTEGER, status TEXT, primary_key TEXT,
 PRIMARY KEY(instance,library,key));
CREATE INDEX IF NOT EXISTS document_title ON documents(instance,title);
CREATE INDEX IF NOT EXISTS document_library ON documents(instance,library);
CREATE INDEX IF NOT EXISTS document_year ON documents(instance,year);
"""


class Index:
    def __init__(self, directory: Path):
        self.directory = directory
        directory.mkdir(parents=True, exist_ok=True)
        self.path = directory / "index.sqlite3"
        self.overrides_path = directory / "overrides.json"
        self.lock = threading.RLock()
        self.recovery = ""
        self.override_warning = ""
        self.overrides = self._load_overrides()
        try:
            with self.connection() as db:
                if db.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                    raise sqlite3.DatabaseError("integrity check")
                db.executescript(SCHEMA)
                db.execute("PRAGMA user_version=1")
        except sqlite3.DatabaseError:
            suffix = f".corrupt-{time.time_ns()}"
            for ending in ["", "-wal", "-shm"]:
                path = Path(str(self.path) + ending)
                if path.exists():
                    path.rename(Path(str(path) + suffix))
            self.recovery = "index_recovered"
            with self.connection() as db:
                db.executescript(SCHEMA)

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        try:
            db.execute("PRAGMA journal_mode=WAL")
            with db:
                yield db
        finally:
            db.close()

    def _load_overrides(self) -> dict:
        try:
            values = json.loads(self.overrides_path.read_text(encoding="utf-8"))
            if not isinstance(values, dict):
                raise ValueError("Invalid overrides")
            for key, value in values.items():
                ident = json.loads(key)
                if (
                    not isinstance(ident, list)
                    or len(ident) != 3
                    or not all(isinstance(part, str) for part in ident)
                    or not isinstance(value, dict)
                ):
                    raise ValueError("Invalid override entry")
                if set(value) - {"state", "path", "primary"} or not all(
                    isinstance(v, str) for v in value.values()
                ):
                    raise ValueError("Invalid override value")
                if value.get("state") and value["state"] not in {"original", "translated", "review"}:
                    raise ValueError("Invalid override state")
            return values
        except FileNotFoundError:
            return {}
        except (ValueError, OSError):
            self.override_warning = "overrides_invalid"
            return {}

    @staticmethod
    def override_id(instance: str, library: str, key: str) -> str:
        return json.dumps([instance, library, key], separators=(",", ":"))

    def override(self, instance: str, library: str, key: str) -> dict:
        with self.lock:
            return dict(self.overrides.get(self.override_id(instance, library, key), {}))

    def set_override(self, instance: str, library: str, key: str, **values) -> None:
        with self.lock:
            if self.override_warning:
                raise ValueError("overrides_invalid")
            ident = self.override_id(instance, library, key)
            updated = {**self.overrides.get(ident, {}), **values}
            self.overrides[ident] = {k: v for k, v in updated.items() if v}
            atomic_json(self.overrides_path, self.overrides)

    def active_instance(self) -> str:
        with self.connection() as db:
            row = db.execute("SELECT value FROM meta WHERE key='active'").fetchone()
            return row[0] if row else ""

    def last_sync(self) -> str:
        with self.connection() as db:
            row = db.execute("SELECT value FROM meta WHERE key='last_sync'").fetchone()
            return row[0] if row else ""

    def libraries(self, instance: str = "") -> list[dict]:
        with self.connection() as db:
            return [
                dict(r)
                for r in db.execute(
                    "SELECT * FROM libraries WHERE instance=? ORDER BY id",
                    (instance or self.active_instance(),),
                )
            ]

    def records(self, instance: str, library: str) -> dict[str, Record]:
        with self.connection() as db:
            return {
                row["key"]: Record(**json.loads(row["payload"]))
                for row in db.execute(
                    "SELECT key,payload FROM items WHERE instance=? AND library=?", (instance, library)
                )
            }

    def collections(self) -> list[dict]:
        with self.connection() as db:
            return [
                dict(row)
                for row in db.execute(
                    "SELECT * FROM collections WHERE instance=? ORDER BY name", (self.active_instance(),)
                )
            ]

    def replace_snapshot(self, instance: str, snapshots: list[tuple], rules: list[dict]) -> None:
        """Commit every library and the active partition together; failed reads never erase cache."""
        with self.lock, self.connection() as db:
            ids = [s[0].id for s in snapshots]
            for table, column in [
                ("libraries", "id"),
                ("items", "library"),
                ("collections", "library"),
                ("documents", "library"),
            ]:
                for old in db.execute(f"SELECT DISTINCT {column} FROM {table} WHERE instance=?", (instance,)):
                    if old[0] not in ids:
                        db.execute(f"DELETE FROM {table} WHERE instance=? AND {column}=?", (instance, old[0]))
            for library, records, collections, version in snapshots:
                db.execute(
                    "INSERT OR REPLACE INTO libraries VALUES(?,?,?,?,?)",
                    (instance, library.id, library.name, library.prefix, version),
                )
                for table in ["items", "collections", "documents"]:
                    db.execute(f"DELETE FROM {table} WHERE instance=? AND library=?", (instance, library.id))
                db.executemany(
                    "INSERT INTO items VALUES(?,?,?,?)",
                    (
                        (instance, library.id, r.key, json.dumps(asdict(r), ensure_ascii=False))
                        for r in records.values()
                    ),
                )
                for raw in collections:
                    data = raw.get("data", raw)
                    db.execute(
                        "INSERT INTO collections VALUES(?,?,?,?,?)",
                        (
                            instance,
                            library.id,
                            data["key"],
                            data.get("name", ""),
                            data.get("parentCollection") or "",
                        ),
                    )
                self._project(db, instance, library.id, records, rules)
            db.execute("INSERT OR REPLACE INTO meta VALUES('active',?)", (instance,))
            db.execute("INSERT OR REPLACE INTO meta VALUES('last_sync',?)", (str(time.time()),))

    def _project(self, db, instance: str, library: str, records: dict[str, Record], rules: list[dict]):
        children: dict[str, list[Record]] = {}
        documents = {}
        for record in records.values():
            if record.kind == "attachment":
                parent = record.parent if record.parent in records else record.key
                children.setdefault(parent, []).append(record)
                if parent == record.key:
                    documents[parent] = record
            elif record.kind not in {"note", "annotation"}:
                documents[record.key] = record
        rows = []
        for key, record in documents.items():
            attachments = []
            for child in children.get(key, []):
                override = self.override(instance, library, child.key)
                path = override.get("path") or child.path
                effective = replace(child, path=path, filename=Path(path).name if path else child.filename)
                state, reason = classify(effective, children[key], rules, override.get("state", ""))
                status, size = file_status(path)
                attachments.append(
                    {
                        "key": child.key,
                        "parent": key,
                        "filename": Path(path).name if path else child.filename,
                        "title": child.title,
                        "path": path,
                        "state": state,
                        "reason": reason,
                        "status": status,
                        "size": size,
                        "path_error": child.path_error,
                    }
                )
            primary = choose_primary(attachments, self.override(instance, library, key).get("primary", ""))
            if not attachments:
                continue
            text = " ".join(
                [
                    record.title,
                    record.authors,
                    record.year,
                    record.doi,
                    *record.tags,
                    *(a["filename"] for a in attachments if a["state"] == AttachmentState.ORIGINAL),
                ]
            )
            rows.append(
                (
                    instance,
                    library,
                    key,
                    record.title,
                    record.authors,
                    record.year,
                    record.doi,
                    json.dumps(record.tags, ensure_ascii=False),
                    json.dumps(record.collections),
                    normalize(text),
                    json.dumps(attachments, ensure_ascii=False),
                    primary["filename"] if primary else "",
                    Path(primary["filename"]).suffix.lower() if primary else "",
                    primary["size"] if primary else 0,
                    primary["status"] if primary else "no_original",
                    primary["key"] if primary else "",
                )
            )
        db.executemany("INSERT INTO documents VALUES(" + ",".join("?" * 16) + ")", rows)

    def reclassify(self, rules: list[dict]) -> None:
        instance = self.active_instance()
        with self.lock, self.connection() as db:
            db.execute("DELETE FROM documents WHERE instance=?", (instance,))
            for library in self.libraries(instance):
                self._project(db, instance, library["id"], self.records(instance, library["id"]), rules)

    def search(self, filters: SearchFilter) -> tuple[list[dict], int]:
        clauses, params = ["instance=?"], [self.active_instance()]
        if filters.library:
            clauses.append("library=?")
            params.append(filters.library)
        if filters.mode == "all":
            clauses.append("primary_key!=''")
        elif filters.mode in {"review", "translated", "errors"}:
            if filters.mode == "errors":
                clauses.append(
                    "EXISTS(SELECT 1 FROM json_each(attachments) WHERE "
                    "json_extract(value,'$.status')!='available' "
                    "AND json_extract(value,'$.state')!='excluded')"
                )
            else:
                clauses.append(
                    "EXISTS(SELECT 1 FROM json_each(attachments) WHERE json_extract(value,'$.state')=?)"
                )
                params.append(filters.mode)
        if filters.collection == "__unfiled__":
            clauses.append("json_array_length(collections)=0")
        elif filters.collection:
            # json_each checks exact collection keys, scoped by library separately.
            clauses.append("EXISTS(SELECT 1 FROM json_each(collections) WHERE value=?)")
            params.append(filters.collection)
        for field_name, value in [("type", filters.file_type), ("year", filters.year)]:
            if value:
                if field_name == "type":
                    clauses.append(
                        "EXISTS(SELECT 1 FROM json_each(attachments) WHERE "
                        "json_extract(value,'$.state')='original' AND "
                        "lower(json_extract(value,'$.filename')) LIKE ?)"
                    )
                    params.append("%" + value.lower())
                else:
                    clauses.append(field_name + "=?")
                    params.append(value)
        if filters.tag:
            clauses.append("EXISTS(SELECT 1 FROM json_each(tags) WHERE value=?)")
            params.append(filters.tag)
        if filters.available:
            clauses.append(
                "EXISTS(SELECT 1 FROM json_each(attachments) WHERE json_extract(value,'$.state')='original'"
                " AND json_extract(value,'$.status')='available')"
            )
        try:
            tokens = shlex.split(filters.text)
        except ValueError:
            tokens = filters.text.split()
        for token in tokens[:20]:
            clauses.append("instr(search,?)>0")
            params.append(normalize(token))
        where = " AND ".join(clauses)
        order = (
            filters.sort
            if filters.sort
            in {"title", "authors", "year", "doi", "type", "filename", "size", "library", "status"}
            else "title"
        )
        with self.connection() as db:
            count = db.execute("SELECT count(*) FROM documents WHERE " + where, params).fetchone()[0]
            rows = db.execute(
                "SELECT * FROM documents WHERE "
                + where
                + f" ORDER BY {order} COLLATE NOCASE "
                + ("DESC" if filters.descending else "ASC")
                + ",library,key LIMIT ? OFFSET ?",
                [*params, max(1, min(filters.limit, 5000)), filters.offset],
            ).fetchall()
            result = [dict(row) for row in rows]
            for row in result:
                for field_name in ["attachments", "tags", "collections"]:
                    row[field_name] = json.loads(row[field_name])
            return result, count

    def rebuild(self) -> None:
        """Only clear this application's index. Separate overrides.json is retained."""
        with self.lock, self.connection() as db:
            for table in ["documents", "items", "collections", "libraries", "meta"]:
                db.execute(f"DELETE FROM {table}")
