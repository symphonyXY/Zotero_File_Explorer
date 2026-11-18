"""Manage marked Markdown children through the bound personal library's local API."""

import hashlib
import json
import re
import secrets
from pathlib import Path

from ..api.client import APIError, LocalAPI
from ..core.models import Library, parse_record
from ..core.paper_cards import (
    CARD_FILENAME,
    CARD_TAG,
    CardDraft,
    CardTarget,
    has_card_marker,
    is_paper_card,
    may_have_card_marker,
)
from .card_transfer import CardTransfer
from .paths import file_url_to_path

PERSONAL = Library("user:0", "personal", "users/0")
ITEMS = "users/0/items"


def new_card(text):
    alphabet = "23456789ABCDEFGHIJKLMNPQRSTUVWXYZ"
    return CardDraft("".join(secrets.choice(alphabet) for _ in range(8)), "", text, creating=True)


class MultipleCards(APIError):
    def __init__(self, keys):
        super().__init__(409, "card_multiple")
        self.keys = frozenset(keys)


class PaperCards:
    def __init__(self, url, instance):
        self.api = LocalAPI(url)
        self.api.server_id = instance
        self.transfer = CardTransfer(self.api, "Zotero File Explorer · Paper Cards")

    def candidates(self, target: CardTarget):
        if target.library != PERSONAL.id:
            raise APIError(403, "card_personal")
        if (
            not target.instance
            or target.instance.startswith("legacy:")
            or target.instance != self.api.server_id
        ):
            raise APIError(501, "card_version")
        if not re.fullmatch(r"[A-Z0-9]{8}", target.parent):
            raise APIError(400, "card_parent")
        parent = self.api.get(f"{ITEMS}/{target.parent}").json()["data"]
        if (
            parent.get("key") != target.parent
            or parent.get("deleted")
            or parent.get("itemType") in {"attachment", "note", "annotation"}
        ):
            raise APIError(400, "card_parent")
        return self._children(target)[0]

    def _children(self, target):
        children, version = self.api.list_all(f"{ITEMS}/{target.parent}/children")
        cards = []
        for item in children:
            record = parse_record(item)
            if record.parent != target.parent or item["data"].get("deleted"):
                continue
            if not is_paper_card(record) and may_have_card_marker(record):
                try:
                    with self._path(record.key).open("rb") as stream:
                        record.card_marker = has_card_marker(stream.read(8192))
                except OSError as error:
                    raise APIError(404, "card_download") from error
            if is_paper_card(record):
                cards.append(record)
        return cards, version

    def _path(self, key):
        try:
            url = self.api.file_url(PERSONAL, key)
        except APIError as error:
            if error.code == 404:
                raise FileNotFoundError from error
            raise
        if url in {"", "false"}:
            raise FileNotFoundError
        return Path(file_url_to_path(url))

    def read(self, target, key):
        if key not in {c.key for c in self.candidates(target)}:
            raise APIError(404, "card_changed")
        try:
            body = self._path(key).read_bytes()
        except FileNotFoundError as error:
            raise APIError(404, "card_download") from error
        try:
            return CardDraft(key, hashlib.md5(body).hexdigest(), body.decode("utf-8"))
        except UnicodeDecodeError as error:
            raise APIError(400, "card_encoding") from error

    def save(self, target, draft, confirmed_keys=frozenset()):
        candidates = self.candidates(target)
        by_key = {c.key: c for c in candidates}
        key = draft.attachment
        if not re.fullmatch(r"[A-Z0-9]{8}", key):
            raise APIError(400, "card_changed")
        if draft.creating and candidates and set(by_key) != {key}:
            raise APIError(409, "card_changed")
        if len(by_key) > 1 and by_key.keys() != confirmed_keys and key in by_key:
            raise MultipleCards(by_key)
        if key not in by_key:
            if not draft.creating:
                raise APIError(404, "card_changed")
            # Fence concurrent creations before committing the new child (including a retry).
            children, version = self._children(target)
            if children:
                raise APIError(409, "card_changed")
            data = dict(
                key=key,
                version=0,
                itemType="attachment",
                parentItem=target.parent,
                linkMode="imported_file",
                filename=CARD_FILENAME,
                title="Paper Card",
                contentType="text/markdown",
                tags=[{"tag": CARD_TAG}],
            )
            try:
                response = self.transfer.post(
                    ITEMS,
                    json.dumps([data]).encode(),
                    "application/json",
                    headers={"If-Unmodified-Since-Version": str(version)},
                )
            except APIError as error:
                if str(error) == "card_conflict":
                    raise APIError(409, "library_changed_during_sync") from error
                raise
            result = json.loads(response)
            if result.get("failed") or key not in {r.key for r in self.candidates(target)}:
                raise APIError(409, "card_changed")
        payload = draft.text.encode("utf-8")

        def current_bytes():
            try:
                return self._path(key).read_bytes()
            except FileNotFoundError as error:
                if draft.creating:
                    return None
                raise APIError(404, "card_download") from error

        def guard():
            live = {r.key: r for r in self.candidates(target)}
            if key not in live or (draft.creating and len(live) != 1):
                raise APIError(409, "card_changed")
            if len(live) > 1 and live.keys() != confirmed_keys:
                raise MultipleCards(live)
            current = current_bytes()
            if current is not None and hashlib.md5(current).hexdigest() != draft.base_md5:
                raise APIError(412, "card_conflict")
            return live[key]

        if current_bytes() != payload:
            record = guard()
            if record.card_marker:
                # Preserve recognition if the author edits away the front matter.
                original = self.api.get(f"{ITEMS}/{key}").json()["data"]
                if original.get("version") != record.version:
                    raise APIError(412, "card_conflict")
                tags = [*original.get("tags", []), {"tag": CARD_TAG}]
                self.transfer.post(
                    f"{ITEMS}/{key}",
                    json.dumps({"tags": tags}).encode(),
                    "application/json",
                    method="PATCH",
                    expected=204,
                    guard=guard,
                    headers={"If-Unmodified-Since-Version": str(record.version)},
                )

            def before_register():
                if guard().filename != record.filename:
                    raise APIError(409, "card_changed")

            self.transfer.upload(
                {"key": key}, payload, draft.base_md5 or None, filename=record.filename, guard=before_register
            )
        saved = self.read(target, key)
        if saved.text != draft.text:
            raise APIError(412, "card_conflict")
        return saved
