"""Zotero 10 local full-file upload. Used by Paper Cards and the live acceptance probe."""

import hashlib
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request

from ..api.client import APIError, LocalAPI
from ..core.paper_cards import CARD_FILENAME


class CardTransfer:
    def __init__(self, api: LocalAPI, app_name: str, authorization_notice=lambda: None):
        self.api = api
        self.app_name = app_name
        self.authorization_notice = authorization_notice
        self.key = ""
        self.remember = False

    def post(
        self, path, data, content_type, *, headers=None, auth=True, expected=200, guard=None, method="POST"
    ):
        request_headers = {
            "Content-Type": content_type,
            "Zotero-API-Version": "3",
            "Zotero-Server-ID": self.api.server_id,
            **(headers or {}),
        }
        if auth:
            if not self.key:
                answer = self.authorize()
                self.key = answer["key"]
                self.remember = answer["remember"]
            request_headers["Zotero-API-Key"] = self.key
            if not self.remember:
                self.key = ""
        if guard:
            guard()
        request = urllib.request.Request(self.api.base_url + path, data, request_headers, method=method)
        timeout = 150 if path == "local/authorize" else 20
        try:
            with self.api.opener.open(request, timeout=timeout) as response:
                if response.status != expected:
                    raise ValueError(f"Unexpected HTTP {response.status} (expected {expected})")
                return response.read()
        except urllib.error.HTTPError as error:
            # Never print tokens, credential-bearing URLs or a user's library metadata.
            if path == "local/authorize" and error.code == 429:
                delay = error.headers.get("Retry-After", "60")
                raise APIError(429, delay) from error
            message = {
                401: "card_authorization",
                403: "card_denied",
                412: "card_conflict",
                429: "card_rate_limit",
            }.get(error.code, "card_write_failed")
            if error.code == 401:
                self.key = ""
            raise APIError(error.code, message) from error

    def authorize(self):
        for attempt in range(2):
            self.authorization_notice()
            try:
                return json.loads(
                    self.post(
                        "local/authorize",
                        json.dumps({"appName": self.app_name}).encode(),
                        "application/json",
                        auth=False,
                    )
                )
            except APIError as error:
                if error.code != 429 or attempt or not str(error).isdigit():
                    raise
                time.sleep(min(60, max(1, int(str(error)))))

    def upload(self, card, data, previous, *, expect_stale=False, filename=CARD_FILENAME, guard=None):
        if isinstance(previous, bytes):
            previous = hashlib.md5(previous).hexdigest()
        conditions = {"If-Match": previous} if previous is not None else {"If-None-Match": "*"}
        path = f"users/0/items/{card['key']}/file"

        def form(values, status=200, guard=None):
            encoded = urllib.parse.urlencode(values).encode()
            options = {"guard": guard} if guard else {}
            return self.post(
                path,
                encoded,
                "application/x-www-form-urlencoded",
                headers=conditions,
                expected=status,
                **options,
            )

        plan = json.loads(
            form(
                {
                    "md5": hashlib.md5(data).hexdigest(),
                    "filename": filename,
                    "filesize": len(data),
                    "mtime": time.time_ns() // 1_000_000,
                    "contentType": "text/markdown",
                }
            )
        )
        if expect_stale:
            raise ValueError("Zotero accepted a stale file precondition; upload stopped")
        if plan.get("exists") == 1:
            return
        token = plan["uploadKey"]
        if not re.fullmatch(r"[A-Za-z0-9]+", token):
            raise ValueError("Invalid upload key")
        target = "local/uploads/" + token
        if plan["url"] != self.api.base_url + target or plan["prefix"] or plan["suffix"]:
            raise ValueError("Unexpected local upload destination or encoding")
        self.post(target, data, plan["contentType"], auth=False, expected=201)
        form({"upload": token}, 204, guard)
