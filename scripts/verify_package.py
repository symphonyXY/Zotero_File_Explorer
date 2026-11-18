import hashlib
import json
import os
import struct
import subprocess
from pathlib import Path

import pefile

from zotero_file_explorer import __version__


def icon_resource_hashes(path):
    """Read actual Windows RT_ICON bytes, independently of Qt's runtime icon."""
    with pefile.PE(str(path), fast_load=True) as executable:
        executable.parse_data_directories(
            directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_RESOURCE"]]
        )
        return {
            hashlib.sha256(
                executable.get_data(data.data.struct.OffsetToData, data.data.struct.Size)
            ).hexdigest()
            for resource in executable.DIRECTORY_ENTRY_RESOURCE.entries if resource.id == 3
            for icon in resource.directory.entries for data in icon.directory.entries
        }


ROOT = Path(__file__).resolve().parents[1]
EXE = ROOT / "build/release/ZoteroFileExplorer/ZoteroFileExplorer.exe"
DATA = ROOT / "build/package-self-check"
env = {k: v for k, v in os.environ.items() if k.upper() not in {"PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV"}}
env["PATH"] = str(Path(os.environ["WINDIR"]) / "System32")
subprocess.run([str(EXE), "--smoke-test", "--data-dir", str(DATA)], cwd=ROOT, env=env, timeout=45, check=True)
result = json.loads((DATA / "self-check.json").read_text(encoding="utf-8"))
assert result["python_bundled"] and result["icon_loaded"] and result["file_urls"] == 1
assert result["version"] == result["qt_application_version"] == __version__
assert not list(EXE.parent.rglob("icu*.dll")), "Qt must use the Windows ICU API, not a PATH collision"
installer = ROOT / f"dist/ZoteroFileExplorer-{__version__}-Setup-x64.exe"
assert installer.is_file()
result["exe_sha256"] = hashlib.sha256(EXE.read_bytes()).hexdigest()
result["installer_sha256"] = hashlib.sha256(installer.read_bytes()).hexdigest()
result["installer_bytes"] = installer.stat().st_size
binary_root = EXE.parent
source_icon = (ROOT / "assets/icons/app.ico").read_bytes()
reserved, kind, count = struct.unpack_from("<HHH", source_icon)
assert reserved == 0 and kind == 1
expected_icons = set()
for n in range(count):
    size, offset = struct.unpack_from("<II", source_icon, 6 + n * 16 + 8)
    expected_icons.add(hashlib.sha256(source_icon[offset:offset + size]).hexdigest())
for executable in (EXE, installer):
    assert expected_icons <= icon_resource_hashes(executable), f"Wrong embedded icon: {executable.name}"
result["embedded_icon_sizes_verified"] = count
result["icon_sha256"] = hashlib.sha256(source_icon).hexdigest()
for name in ("app.ico", "app.png"):
    bundled_asset = binary_root / "_internal/assets/icons" / name
    assert bundled_asset.read_bytes() == (ROOT / "assets/icons" / name).read_bytes()
assert not list(binary_root.rglob("concepts"))
assert not list(binary_root.rglob("app-source.png"))
result["dlls"] = sorted(p.name for p in binary_root.rglob("*.dll"))
assert not list(binary_root.rglob("*.pdf")) and not list(binary_root.rglob("*.sqlite*"))
(ROOT / "dist/SHA256SUMS.txt").write_text(
    result["installer_sha256"] + "  " + installer.name + "\n", encoding="ascii"
)
print(json.dumps({k: v for k, v in result.items() if k != "dlls"}, indent=2))
