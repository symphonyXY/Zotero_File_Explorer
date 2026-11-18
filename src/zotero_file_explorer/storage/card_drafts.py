"""One recoverable local draft per document. Writes execute in submission order."""

import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from threading import Lock

from ..core.paper_cards import CardDraft, CardTarget
from .config import atomic_json


class CardDrafts:
    def __init__(self, directory):
        self.directory = directory / "paper-card-drafts"
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="card-draft")
        self.lock = Lock()
        self.latest = {}

    def path(self, target):
        key = hashlib.sha256(json.dumps(asdict(target), sort_keys=True).encode()).hexdigest()
        return self.directory / (key + ".json")

    def load(self, target: CardTarget):
        try:
            record = json.loads(self.path(target).read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        if record["target"] != asdict(target):
            raise ValueError("card_draft_error")
        return CardDraft(**record["draft"])

    def put(self, target, draft):
        marker = object()
        with self.lock:
            self.latest[target] = marker

        def write():
            with self.lock:
                if self.latest.get(target) is not marker:
                    return
            path = self.path(target)
            if draft is None:
                path.unlink(missing_ok=True)
            else:
                atomic_json(path, {"target": asdict(target), "draft": asdict(draft)})
            with self.lock:
                if self.latest.get(target) is marker:
                    self.latest.pop(target)

        return self.executor.submit(write)
