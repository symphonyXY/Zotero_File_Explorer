"""Phase 1 acceptance on personal-library synthetic items, separate from Explorer."""

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from uuid import UUID

from zotero_file_explorer.api.client import APIError, LocalAPI
from zotero_file_explorer.services.card_transfer import CardTransfer
from zotero_file_explorer.services.paths import file_url_to_path

ITEMS = "users/0/items"
FILENAME = "PaperCard.md"
TAG = "zfe-paper-card-phase1"
APP_NAME = "Zotero File Explorer (Paper Cards test)"


def fixture(run):
    """Keys are reproducible on retry and on device B, independent of its server ID."""
    alphabet = "23456789ABCDEFGHIJKLMNPQRSTUVWXYZ"

    def key(role):
        digest = hashlib.sha256(f"{run}/{role}".encode()).digest()
        return "".join(alphabet[b % len(alphabet)] for b in digest[:8])

    parent = dict(key=key("paper"), itemType="journalArticle", title=f"Paper Cards test {run}")
    card = dict(key=key("card"), itemType="attachment", parentItem=parent["key"],
                linkMode="imported_file", title="Paper Card", filename=FILENAME, contentType="text/markdown")
    body = f"---\ncard_type: explorer-paper-card\nschema_version: 1\n---\n\n# 记忆线索\n\n{run}\n"
    return parent, card, (body + "\n初次创建。\n").encode(), (body + "\n第二版：已编辑。\n").encode()


class Probe(CardTransfer):
    def __init__(self):
        self.api = LocalAPI()
        info = self.api.probe()
        version = info.headers.get("x-zotero-version", "")
        print(f"Zotero {version}, Local API {self.api.api_version}", flush=True)
        if not self.api.server_id or not re.match(r"^\d+", version) or int(version.split(".")[0]) < 10:
            raise ValueError("Zotero 10+ and a server ID are required")
        super().__init__(self.api, APP_NAME, lambda: print("Waiting for Zotero authorization...", flush=True))

    def item(self, spec, *, create):
        path = f"{ITEMS}/{spec['key']}"
        try:
            data = self.api.get(path).json()["data"]
        except APIError as error:
            if error.code != 404 or not create:
                raise
            obj = {**spec, "version": 0, "tags": [{"tag": TAG}]}
            result = json.loads(self.post(ITEMS, json.dumps([obj]).encode(), "application/json"))
            if result.get("failed"):
                code = result["failed"]["0"]["code"]
                raise ValueError(f"Test item creation rejected ({code})") from None
            data = self.api.get(path).json()["data"]
        if (any(data.get(k) != v for k, v in spec.items())
                or TAG not in {t["tag"] for t in data["tags"]} or data.get("deleted")):
            raise ValueError("Test item identity changed; use Zotero to inspect the fixture")
        return data

    def read(self, card):
        url = self.api.get(f"{ITEMS}/{card['key']}/file/view/url").body.decode()
        if url in {"", "false"}:
            raise FileNotFoundError("Zotero returned no local file")
        return Path(file_url_to_path(url)).read_bytes()

    def run(self, run, write):
        parent, card, first, final = fixture(run)
        self.item(parent, create=write)
        metadata = self.item(card, create=write)
        children, _ = self.api.list_all(f"{ITEMS}/{parent['key']}/children")
        candidates = [c["key"] for c in children if TAG in {t["tag"] for t in c["data"]["tags"]}]
        if candidates != [card["key"]]:
            raise ValueError("Missing or ambiguous test child; inspect the parent in Zotero")
        try:
            current = self.read(card)
        except FileNotFoundError:
            if not write or metadata.get("md5"):
                raise ValueError("Download the test attachment in Zotero before verification") from None
            self.upload(card, first, None)
            current = self.read(card)
            if current != first:
                raise ValueError("Initial UTF-8 content did not round-trip") from None
        if write and current == first:
            self.upload(card, final, first)
            current = self.read(card)
        if current != final:
            raise ValueError("Unexpected attachment contents; the existing file is preserved")
        if write:
            try:
                self.upload(card, first, first, expect_stale=True)
            except APIError as error:
                if error.code != 412:
                    raise
            self.item(card, create=False)
            if self.read(card) != final:
                raise ValueError("Contents changed after stale write")
        digest = hashlib.sha256(final).hexdigest()
        print(f"Verified parent={parent['key']}, attachment={card['key']}, SHA256={digest}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("write-test", "verify"))
    parser.add_argument("run", type=UUID, help="Use the same test UUID for retries and on both devices")
    args = parser.parse_args()
    print(f"Test paper: Paper Cards test {args.run}", flush=True)
    try:
        Probe().run(args.run, args.action == "write-test")
    except (ValueError, OSError, APIError, KeyError) as error:
        print(f"Verification incomplete: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
