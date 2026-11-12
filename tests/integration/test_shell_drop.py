"""Native Shell IDropTarget integration; this is not a mouse-gesture acceptance test."""

import ctypes
import hashlib
import subprocess
import sys
from pathlib import Path

import pytest

from zotero_file_explorer.platform.files import copy_files

pytestmark = [pytest.mark.windows, pytest.mark.skipif(sys.platform != "win32", reason="Windows Shell COM")]


@pytest.mark.parametrize("flush", [False, True], ids=["live-qt", "flushed-clipboard"])
def test_native_shell_drop_target(qapp, qtbot, tmp_path, flush):
    source = tmp_path / "source 中文"
    target = tmp_path / "drop destination"
    source.mkdir()
    target.mkdir()
    files = [source / "原始 文献 #%.txt", source / "supplement.txt"]
    for n, path in enumerate(files):
        path.write_bytes(b"Synthetic native drop fixture " + str(n).encode())
    hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    copy_files([str(p) for p in files])
    qapp.processEvents()
    if flush:
        # Exercise both the application's live data object and a materialized clipboard.
        assert ctypes.OleDLL("ole32").OleFlushClipboard() == 0
    helper = Path(__file__).resolve().parents[2] / "scripts/shell_drop_probe.py"
    process = subprocess.Popen(
        [sys.executable, str(helper), str(target)], stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    try:
        try:
            qtbot.waitUntil(lambda: process.poll() is not None, timeout=20000)
        except Exception:
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True, check=False
            )
            stdout, stderr = process.communicate(timeout=5)
            pytest.fail(
                "Native drop timed out: " + stdout.decode(errors="replace") + stderr.decode(errors="replace")
            )
        stdout, stderr = process.communicate()
        assert process.returncode == 0, stderr.decode(errors="replace")
        assert b"DROPEFFECT_COPY" in stdout
        for path in files:
            assert path.exists()
            assert hashlib.sha256(path.read_bytes()).hexdigest() == hashes[path.name]
            assert hashlib.sha256((target / path.name).read_bytes()).hexdigest() == hashes[path.name]
    finally:
        if process.poll() is None:
            process.kill()
            process.communicate()
        qapp.clipboard().clear()
