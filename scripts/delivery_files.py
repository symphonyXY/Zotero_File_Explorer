"""Files distributed with the desktop app and its corresponding production source."""

import hashlib
import json
import re
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

GUIDES = ("docs/user/installation.md", "docs/user/user-guide.md")
SOURCE_FILES = {
    "LICENSE", "THIRD_PARTY_NOTICES.md", "README.md", "pyproject.toml", "requirements-dev.lock",
    "assets/icons/app-source.png", "assets/icons/app.ico", "assets/icons/app.png",
    "scripts/entry.py", "scripts/package_notices.py", "scripts/delivery_files.py",
    "scripts/dev-setup.ps1", "scripts/install-build-tools.ps1", *GUIDES,
}


def source_member(name):
    if name.startswith("src/zotero_file_explorer/"):
        return name.endswith(".py") and "__pycache__" not in Path(name).parts
    return name in SOURCE_FILES or name.startswith(("installer/", "config/", "licenses/"))


def delivery_docs(version, read, *, source=False):
    heading = f"# Zotero File Explorer {version}\n\n"
    readme = heading + (
        "在 Windows 上浏览、检索、复制和拖放 Zotero 文献附件。\n\n"
        "[安装说明](docs/user/installation.md) · [使用指南](docs/user/user-guide.md)\n"
    )
    if source:
        readme += (
            "\n## 从源码构建\n\n在 Windows x64 安装 Python 3.13，进入源码目录执行下列命令。"
            "最后一步使用 Inno Setup 6。构建输出位于 build 和 dist。\n\n```powershell\n"
            ".\\scripts\\dev-setup.ps1\n"
            ".\\.venv\\Scripts\\python.exe -m PyInstaller --workpath build/pyinstaller "
            "--distpath build/release installer/ZoteroFileExplorer.spec\n"
            ".\\.venv\\Scripts\\python.exe scripts/package_notices.py\n"
            ".\\scripts\\install-build-tools.ps1\n"
            ".\\build\\tools\\inno\\ISCC.exe installer/ZoteroFileExplorer.iss\n```\n"
        )
    docs = {"README.md": readme.encode()}
    for name in GUIDES:
        text = read(name).decode("utf-8-sig")
        # Repository navigation is not installed. Keep the two local guide links.
        lines = [line for line in text.splitlines() if not line.startswith(("[安装说明]", "[使用指南]"))]
        text = re.sub(r"\[([^]\n]+)\]\(\.\./[^)]+\)", r"\1", "\n".join(lines))
        text = text.replace("；具体 Zotero 版本和未覆盖范围以验证记录为准。", "。")
        other = (
            "[安装说明](installation.md)" if name.endswith("user-guide.md")
            else "[使用指南](user-guide.md)"
        )
        docs[name] = (text.rstrip() + "\n\n" + other + "\n").encode()
    return docs


def write_sources(target, version, names, read):
    """Write and re-read a source archive, including only its version's production inputs."""
    docs = delivery_docs(version, read, source=True)
    entries = []
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(".tmp")
    with ZipFile(temporary, "x", ZIP_DEFLATED, compresslevel=6) as archive:
        for name in sorted(set(names) | docs.keys()):
            if source_member(name):
                data = docs[name] if name in docs else read(name)
                archive.writestr(name, data)
                entries.append({"path": name, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()})
    with ZipFile(temporary) as archive:
        assert set(archive.namelist()) == {e["path"] for e in entries}
        assert all(hashlib.sha256(archive.read(e["path"])).hexdigest() == e["sha256"] for e in entries)
    temporary.replace(target)
    report = {"files": entries, "total_bytes": sum(e["bytes"] for e in entries), "errors": []}
    target.with_suffix(".manifest.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
