"""Keep exact upstream source archives and extract only notice/license metadata."""

import concurrent.futures
import hashlib
import json
import tarfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "dist/ThirdPartySources"
NOTICES = ROOT / "licenses"
OUT.mkdir(parents=True, exist_ok=True)
NOTICES.mkdir(exist_ok=True)
URLS = [
    "https://download.qt.io/archive/qt/6.10/6.10.2/submodules/qtbase-everywhere-src-6.10.2.tar.xz",
    "https://download.qt.io/archive/qt/6.10/6.10.2/submodules/qtsvg-everywhere-src-6.10.2.tar.xz",
    "https://download.qt.io/archive/qt/6.10/6.10.2/submodules/qtimageformats-everywhere-src-6.10.2.tar.xz",
    "https://download.qt.io/official_releases/QtForPython/pyside6/PySide6-6.10.2-src/pyside-setup-everywhere-src-6.10.2.tar.xz",
]


def fetch(url):
    path = OUT / url.rsplit("/", 1)[-1]
    if not path.exists():
        # master.qt.io is Qt's official origin, avoiding a geographically selected
        # mirror with a broken TLS chain. Certificate verification stays enabled.
        download_url = url.replace("https://download.qt.io/", "https://master.qt.io/")
        with (
            urllib.request.urlopen(download_url, timeout=45) as response,
            path.with_suffix(".part").open("wb") as stream,
        ):
            while chunk := response.read(1024 * 1024):
                stream.write(chunk)
        path.with_suffix(".part").rename(path)
    with tarfile.open(path, "r:xz") as archive:
        for entry in archive:
            if not entry.isfile():
                continue
            parts = Path(entry.name).parts
            if ".." in parts or Path(entry.name).is_absolute():
                raise ValueError("Unsafe source archive path")
            filename = Path(entry.name).name.lower()
            if (
                any(word in filename for word in ["license", "copying", "copyright", "notice"])
                or "LICENSES" in parts
                or filename == "qt_attribution.json"
            ) and entry.size < 2_000_000:
                target = NOTICES / entry.name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(archive.extractfile(entry).read())
    result = {
        "url": url,
        "file": path.name,
        "bytes": path.stat().st_size,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }
    print(path.name, result["bytes"], flush=True)
    return result


if __name__ == "__main__":
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(fetch, URLS))
    (OUT / "manifest.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    (ROOT / "docs/evidence/third-party-sources.json").write_text(
        json.dumps(results, indent=2), encoding="utf-8"
    )
