from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

from ..core.models import Library


class APIError(Exception):
    def __init__(self, code: int, message: str):
        super().__init__(message)
        self.code = code


class InstanceChanged(APIError):
    def __init__(self):
        super().__init__(412, "instance_changed")


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise APIError(code, "unexpected_redirect")


@dataclass
class Response:
    body: bytes
    headers: dict[str, str]

    def json(self):
        try:
            return json.loads(self.body)
        except (ValueError, UnicodeError) as error:
            raise APIError(0, "invalid_json") from error

    @property
    def version(self) -> int:
        try:
            return int(self.headers.get("last-modified-version", "0"))
        except ValueError as error:
            raise APIError(0, "invalid_version") from error


class LocalAPI:
    """GET-only, loopback-only, no system proxy, no following file/network redirects."""

    def __init__(self, base_url: str = "http://127.0.0.1:23119/api/", timeout: float = 8):
        parsed = urllib.parse.urlsplit(base_url)
        if (
            parsed.scheme != "http"
            or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or parsed.path.rstrip("/") != "/api"
        ):
            raise ValueError("Only a local Zotero /api/ endpoint is allowed")
        # Zotero listens on IPv4; using localhost may resolve to an unavailable IPv6 address.
        port = parsed.port or 23119
        self.base_url = f"http://127.0.0.1:{port}/api/"
        self.timeout = timeout
        self.server_id = ""
        self.api_version = "3"
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())

    def get(self, path: str = "", params: dict | None = None) -> Response:
        if path.startswith(("/", ".")) or ":" in path or ".." in path.split("/"):
            raise ValueError("Invalid API path")
        headers = {"Zotero-API-Version": self.api_version, "Accept": "application/json"}
        if self.server_id:
            headers["Zotero-Server-ID"] = self.server_id
        url = self.base_url + path
        if params:
            url += "?" + urllib.parse.urlencode(params)
        request = urllib.request.Request(url, headers=headers, method="GET")
        try:
            with self.opener.open(request, timeout=self.timeout) as response:
                result = Response(
                    response.read(128 * 1024 * 1024), {k.lower(): v for k, v in response.headers.items()}
                )
        except urllib.error.HTTPError as error:
            if error.code == 412:
                raise InstanceChanged() from error
            raise APIError(
                error.code,
                {403: "api_disabled", 404: "not_found", 501: "unsupported_api"}.get(error.code, "api_error"),
            ) from error
        except (OSError, urllib.error.URLError, TimeoutError) as error:
            raise APIError(0, "offline") from error
        current_id = result.headers.get("zotero-server-id", "")
        if self.server_id and current_id != self.server_id:
            raise InstanceChanged()
        return result

    def probe(self) -> Response:
        self.server_id = ""
        response = self.get()
        self.api_version = response.headers.get("zotero-api-version", "3")
        if self.api_version != "3":
            raise APIError(501, "unsupported_api")
        self.server_id = response.headers.get("zotero-server-id", "")
        return response

    def list_all(self, path: str, params: dict | None = None) -> tuple[list[dict], int]:
        start, items, version = 0, [], None
        while True:
            response = self.get(path, {**(params or {}), "limit": 100, "start": start})
            data = response.json()
            if not isinstance(data, list):
                raise APIError(0, "invalid_list")
            if version is not None and version != response.version:
                raise APIError(409, "library_changed_during_sync")
            version = response.version
            items.extend(data)
            start += len(data)
            if len(data) < 100:
                return items, version or 0

    def libraries(self) -> list[Library]:
        groups, _ = self.list_all("users/0/groups")
        result = [Library("user:0", "personal", "users/0")]
        for group in groups:
            data = group.get("data", group)
            ident = str(group.get("id") or data.get("id") or "")
            if not ident.isdigit():
                raise APIError(0, "invalid_group")
            result.append(Library("group:" + ident, str(data.get("name", ident)), "groups/" + ident))
        return result

    def file_url(self, library: Library, key: str) -> str:
        if len(key) != 8 or not key.isalnum():
            raise ValueError("Invalid item key")
        return self.get(f"{library.prefix}/items/{key}/file/view/url").body.decode("utf-8").strip()
