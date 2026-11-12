"""Exercise install/reinstall/shortcut migration in a separate acceptance namespace."""

import hashlib
import json
import os
import subprocess
from pathlib import Path

from zotero_file_explorer import __version__

ROOT = Path(__file__).resolve().parents[1]
TARGET = (ROOT / "build/install-check").resolve()
assert TARGET.is_relative_to(ROOT / "build") and TARGET.name == "install-check"
INSTALLER = (
    ROOT / f"build/acceptance-installer/ZoteroFileExplorer-{__version__}-Setup-x64 Acceptance Test.exe"
)


def powershell(script, **variables):
    env = dict(os.environ)
    env.update(variables)
    output = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
        env=env, check=True, capture_output=True, text=True, encoding="utf-8", timeout=30,
    )
    return json.loads(output.stdout)


def shortcut(path, *, target="", icon=""):
    # COM reads/writes .lnk file metadata; no UI automation or interpolated commands.
    return powershell(
        """
        $ErrorActionPreference = 'Stop'
        [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
        $shell = New-Object -ComObject WScript.Shell
        $link = $shell.CreateShortcut($env:ZFE_LINK_PATH)
        if ($env:ZFE_LINK_TARGET) { $link.TargetPath = $env:ZFE_LINK_TARGET }
        if ($env:ZFE_LINK_ICON) { $link.IconLocation = $env:ZFE_LINK_ICON }
        if ($env:ZFE_LINK_TARGET -or $env:ZFE_LINK_ICON) { $link.Save() }
        @{ target = $link.TargetPath; icon = $link.IconLocation;
           arguments = $link.Arguments } | ConvertTo-Json -Compress
        """,
        ZFE_LINK_PATH=str(path), ZFE_LINK_TARGET=target, ZFE_LINK_ICON=icon,
    )


def install(tasks, label):
    subprocess.run(
        [str(INSTALLER), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CURRENTUSER",
         f"/DIR={TARGET}", f"/TASKS={tasks}", f"/LOG={ROOT / 'build' / (label + '.log')}"],
        cwd=ROOT, timeout=120, check=True,
    )


assert not TARGET.exists(), "Test destination already exists; inspect it before reusing."
folders = powershell(
    """
    [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
    @{ desktop = [Environment]::GetFolderPath('DesktopDirectory');
       programs = [Environment]::GetFolderPath('Programs') } | ConvertTo-Json -Compress
    """
)
desktop = Path(folders["desktop"]) / "Zotero File Explorer Acceptance Test.lnk"
start_links = [
    Path(folders["programs"]) / (name + " Acceptance Test.lnk")
    for name in ["Zotero File Explorer", "Zotero File Explorer Quick"]
]
assert not any(path.exists() for path in [desktop, *start_links]), "Existing test links: inspect first."
icon_hash = hashlib.sha256((ROOT / "assets/icons/app.ico").read_bytes()).hexdigest()
installed_icon = TARGET / "icons" / f"app-{icon_hash}.ico"
exe = TARGET / "ZoteroFileExplorer.exe"
result = {
    "installer_sha256": hashlib.sha256(INSTALLER.read_bytes()).hexdigest(),
    "isolated_identity": True,
    "note": "Same payload and ISS; test-only AppId and all shortcut suffixes isolate user installs.",
}
install("", "installer-fresh-test")
assert exe.is_file() and (TARGET / "unins000.exe").is_file()
assert not desktop.exists(), "Optional desktop shortcut was created without selection."
result["fresh_install_without_desktop"] = True
assert hashlib.sha256(installed_icon.read_bytes()).hexdigest() == icon_hash

# A matching display name alone must not authorize replacing a foreign shortcut.
foreign_target = str(Path(os.environ["WINDIR"]) / "System32/notepad.exe")
shortcut(desktop, target=foreign_target, icon=foreign_target + ",0")
foreign_bytes = desktop.read_bytes()
install("", "installer-foreign-link-test")
assert desktop.read_bytes() == foreign_bytes, "Unchecked task changed an unrelated link."
desktop.unlink()  # This exact temporary link was created and fingerprinted above.
result["unrelated_desktop_link_preserved"] = True

install("desktopicon", "installer-desktop-test")
assert desktop.is_file()
assert shortcut(desktop)["icon"].lower() == (str(installed_icon) + ",0").lower()
result["selected_desktop_created"] = True

# Reproduce the reported legacy metadata: default EXE icon at an unchanged path.
shortcut(desktop, icon=",0")
assert shortcut(desktop)["icon"] == ",0"
install("", "installer-legacy-reinstall-test")
links = [shortcut(path) for path in [desktop, *start_links]]
assert all(Path(link["target"]) == exe for link in links)
assert all(link["icon"].lower() == (str(installed_icon) + ",0").lower() for link in links)
assert links[2]["arguments"] == "--quick"
result["legacy_desktop_refreshed_with_task_off"] = True
result["start_menu_shortcuts"] = [path.is_file() for path in start_links]
result["shortcut_icon_file"] = installed_icon.relative_to(TARGET).as_posix()
result["shortcut_icon_sha256"] = icon_hash

env = {k: v for k, v in os.environ.items() if k.upper() not in {"PYTHONHOME", "PYTHONPATH", "VIRTUAL_ENV"}}
env["PATH"] = str(Path(os.environ["WINDIR"]) / "System32")
data = ROOT / "build/installed-self-check"
subprocess.run([str(exe), "--smoke-test", "--data-dir", str(data)], cwd=ROOT, env=env, timeout=45, check=True)
result["installed_self_check"] = json.loads((data / "self-check.json").read_text(encoding="utf-8"))
assert result["installed_self_check"]["python_bundled"] and result["installed_self_check"]["icon_loaded"]
result["installed_exe_sha256"] = hashlib.sha256(exe.read_bytes()).hexdigest()
assert result["installed_exe_sha256"] == hashlib.sha256(
    (ROOT / "build/release/ZoteroFileExplorer/ZoteroFileExplorer.exe").read_bytes()
).hexdigest()
subprocess.run(
    [str(TARGET / "unins000.exe"), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART",
     f"/LOG={ROOT / 'build/uninstaller-test.log'}"],
    cwd=ROOT, timeout=120, check=True,
)
result["uninstall_removed_exe"] = not exe.exists()
result["uninstall_removed_shortcuts"] = not any(path.exists() for path in [desktop, *start_links])
result["uninstall_removed_icon"] = not installed_icon.exists()
result["application_data_retained"] = (data / "self-check.json").exists()
assert all(result[key] for key in ["uninstall_removed_exe", "uninstall_removed_shortcuts",
                                   "uninstall_removed_icon", "application_data_retained"])
(ROOT / f"docs/evidence/installer-{__version__}.json").write_text(
    json.dumps(result, indent=2), encoding="utf-8"
)
print(json.dumps(result, indent=2))
