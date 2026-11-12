from __future__ import annotations

import configparser
import json
import os
import re
import urllib.parse
import urllib.request
from pathlib import Path, PureWindowsPath

from ..core.models import Record


def file_url_to_path(value: str) -> str:
    parsed = urllib.parse.urlsplit(value)
    if parsed.scheme != "file" or parsed.query or parsed.fragment:
        raise ValueError("Not a local file URL")
    path = urllib.request.url2pathname(parsed.path)
    if parsed.netloc and parsed.netloc.lower() != "localhost":
        path = "\\\\" + parsed.netloc + "\\" + path.lstrip("\\/")
    if "\x00" in path or not (Path(path).is_absolute() or PureWindowsPath(path).is_absolute()):
        raise ValueError("Not an absolute file path")
    return path


def detected_directories() -> tuple[list[str], str]:
    """Read prefs only, never open or change zotero.sqlite."""
    roots = [Path(os.environ.get("APPDATA", "")) / "Zotero/Zotero", Path.home() / ".zotero/zotero"]
    found, base = [], ""
    for root in roots:
        parser = configparser.ConfigParser()
        try:
            parser.read(root / "profiles.ini", encoding="utf-8")
            profiles = [
                root / parser[s]["Path"]
                if parser[s].get("IsRelative", "1") == "1"
                else Path(parser[s]["Path"])
                for s in parser.sections()
                if "Path" in parser[s]
            ]
        except (OSError, configparser.Error):
            profiles = []
        for profile in profiles:
            try:
                prefs = (profile / "prefs.js").read_text(encoding="utf-8")
                for key in ["dataDir", "baseAttachmentPath"]:
                    match = re.search(
                        r'user_pref\("extensions\.zotero\.' + key + r'",\s*("(?:\\.|[^"\\])*")\);', prefs
                    )
                    if match:
                        value = json.loads(match[1])
                        if key == "dataDir" and Path(value).is_dir():
                            found.append(value)
                        elif key == "baseAttachmentPath":
                            base = value
            except (OSError, ValueError):
                continue
    conventional = Path.home() / "Zotero"
    if conventional.is_dir():
        found.append(str(conventional))
    return list(dict.fromkeys(found)), base


def fallback_path(record: Record, data_directory: str, attachment_base: str) -> str:
    """Fallback uses explicit API metadata, never scans random storage directories."""
    raw = record.path
    if raw.startswith("storage:"):
        relative = raw.removeprefix("storage:")
        if not data_directory or Path(relative).name != relative or "\\" in relative:
            return ""
        return str(Path(data_directory) / "storage" / record.key / relative)
    if raw.startswith("attachments:"):
        if not attachment_base:
            return ""
        root = Path(attachment_base).resolve()
        relative = raw.removeprefix("attachments:").replace("\\", "/")
        candidate = (root / relative).resolve()
        if candidate.is_relative_to(root):
            return str(candidate)
        return ""
    if raw and Path(raw).is_absolute():
        return raw
    # Stored-file filename alone is documented API metadata, but require a
    # configured data directory and verify the candidate exists before using it.
    if data_directory and record.link_mode in {"imported_file", "imported_url"}:
        filename = record.filename
        if filename and Path(filename).name == filename and "\\" not in filename:
            candidate = Path(data_directory) / "storage" / record.key / filename
            if candidate.is_file():
                return str(candidate)
    return ""


def file_status(path: str) -> tuple[str, int]:
    if not path:
        return "not_downloaded", 0
    try:
        stat = Path(path).stat()
        if not Path(path).is_file():
            return "missing", 0
        if not os.access(path, os.R_OK):
            return "permission", stat.st_size
        return "available", stat.st_size
    except PermissionError:
        return "permission", 0
    except (OSError, ValueError):
        return "missing", 0


def valid_file_paths(paths: list[str]) -> list[str]:
    result, seen = [], set()
    for raw in paths:
        if not raw or not Path(raw).is_absolute() or "\x00" in raw:
            continue
        path = str(Path(raw).resolve())
        canonical = os.path.normcase(path)
        if canonical not in seen and file_status(path)[0] == "available":
            # Opening without reading also checks Windows ACLs and sharing modes.
            try:
                with open(path, "rb"):
                    pass
            except OSError:
                continue
            seen.add(canonical)
            result.append(path)
    return result
