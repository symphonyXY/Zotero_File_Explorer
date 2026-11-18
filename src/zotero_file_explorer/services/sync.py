from __future__ import annotations

import hashlib
from pathlib import Path

from ..api.client import APIError, LocalAPI
from ..core.models import SUPPORTED, parse_record
from ..core.paper_cards import has_card_marker, is_paper_card, may_have_card_marker
from ..storage.config import Settings
from ..storage.index import Index
from .paths import fallback_path, file_status, file_url_to_path


class SyncService:
    def __init__(self, index: Index, settings: Settings, client: LocalAPI | None = None):
        self.index, self.settings = index, settings
        self.api = client or LocalAPI(settings.api_url)

    def synchronize(
        self, force_paths: bool = False, progress=lambda text: None, cancelled=lambda: False
    ) -> dict:
        self.api.probe()
        # Legacy versions have no trustworthy local versions; always do full reads.
        binding = (
            str(Path(self.settings.data_directory).resolve())
            if self.settings.data_directory
            else self.api.base_url
        )
        instance = self.api.server_id or "legacy:" + hashlib.sha256(binding.encode()).hexdigest()[:24]
        libraries = self.api.libraries()
        previous = {lib["id"]: lib for lib in self.index.libraries(instance)}
        snapshots = []
        for library in libraries:
            if cancelled():
                raise APIError(0, "cancelled")
            progress(library.name)
            last_version = previous.get(library.id, {}).get("version", 0)
            old = self.index.records(instance, library.id)
            # A full version/key inventory detects hard deletions and trash even
            # when /deleted is unsupported. It also provides a consistency fence.
            inventory = self.api.get(library.prefix + "/items", {"format": "versions"})
            versions = inventory.json()
            if not isinstance(versions, dict):
                raise APIError(0, "invalid_inventory")
            version = inventory.version
            use_since = bool(self.api.server_id and old and 0 < last_version <= version)
            params = {"since": last_version} if use_since else {}
            changed, data_version = self.api.list_all(library.prefix + "/items", params)
            collections, collection_version = self.api.list_all(library.prefix + "/collections")
            if version != data_version or version != collection_version:
                raise APIError(409, "library_changed_during_sync")
            records = {k: v for k, v in old.items() if k in versions} if use_since else {}
            changed_keys = set()
            for raw in changed:
                record = parse_record(raw)
                if record.key in versions:
                    records[record.key] = record
                    changed_keys.add(record.key)
            if set(records) != set(versions):
                raise APIError(409, "incomplete_inventory")
            for number, record in enumerate(records.values()):
                if cancelled():
                    raise APIError(0, "cancelled")
                if record.kind != "attachment" or record.link_mode == "linked_url":
                    continue
                supported = Path(record.filename or record.path).suffix.lower() in SUPPORTED
                card_file = is_paper_card(record) or may_have_card_marker(record)
                if not supported and not card_file:
                    continue
                if force_paths or record.key in changed_keys or file_status(record.path)[0] != "available":
                    previous_path = old.get(record.key).path if record.key in old else ""
                    metadata_path = record.path
                    try:
                        record.path = file_url_to_path(self.api.file_url(library, record.key))
                        record.path_error = ""
                    except APIError as error:
                        if error.code not in {404, 400, 501}:
                            raise
                        record.path = fallback_path(
                            record, self.settings.data_directory, self.settings.attachment_base
                        )
                        if not record.path and previous_path and record.key not in changed_keys:
                            record.path = previous_path
                        record.path_error = error.args[0]
                    except (ValueError, UnicodeError):
                        record.path = ""
                        record.path_error = "invalid_file_url"
                    if record.path.startswith(("storage:", "attachments:")):
                        record.path = ""
                    # Preserve the API filename independently from attachment title.
                    if record.path and not card_file:
                        record.filename = Path(record.path).name
                    elif not record.filename and metadata_path:
                        record.filename = Path(metadata_path).name
                record.card_marker = False
                if may_have_card_marker(record) and not is_paper_card(record):
                    try:
                        with Path(record.path).open("rb") as stream:
                            record.card_marker = has_card_marker(stream.read(8192))
                        record.path_error = ""
                    except OSError:
                        record.path_error = "card_download"
                if number % 100 == 0:
                    progress(f"{library.name} · {number + 1}/{len(records)}")
            final = self.api.get(library.prefix + "/items", {"format": "versions"})
            if final.version != version or final.json() != versions:
                raise APIError(409, "library_changed_during_sync")
            snapshots.append((library, records, collections, version))
        if cancelled():
            raise APIError(0, "cancelled")
        self.index.replace_snapshot(instance, snapshots, self.settings.rules)
        return {
            "instance": instance,
            "libraries": len(libraries),
            "items": sum(len(s[1]) for s in snapshots),
            "legacy": not bool(self.api.server_id),
        }
