"""Deletion safety is tested against isolated Git repos, never the real workspace."""

import importlib.util
import json
import os
import py_compile
import subprocess
from pathlib import Path

import pytest


def load_script(name):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).parents[2] / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_publication_keeps_community_docs_and_excludes_private_design_inputs(tmp_path):
    root = tmp_path / "public-source"
    root.mkdir()
    git(root, "init")
    (root / ".gitignore").write_text("assets/icons/concepts/\n", encoding="utf-8")
    for name in ("CONTRIBUTING.md", "SECURITY.md"):
        (root / name).write_text("Public project guidance", encoding="utf-8")
    concepts = root / "assets/icons/concepts"
    concepts.mkdir(parents=True)
    (concepts / "private-prompts.json").write_text(str(Path.home()), encoding="utf-8")
    report = publication.audit_repository(root)
    assert not report["errors"]
    assert {entry["path"] for entry in report["files"]} == {".gitignore", "CONTRIBUTING.md", "SECURITY.md"}


clean = load_script("clean_project")
docs = load_script("check_docs")
publication = load_script("check_repository")


def git(root, *args):
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


@pytest.fixture
def repository(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init")
    (root / ".gitignore").write_text("__pycache__/\nwork/\n", encoding="utf-8")
    (root / "src").mkdir()
    source = root / "src" / "sample.py"
    source.write_text("answer = 42\n", encoding="utf-8")
    git(root, "add", ".gitignore", "src/sample.py")
    cache = Path(py_compile.compile(str(source), doraise=True))
    return root, cache


def test_cleanup_default_preview_preserves_unknown_and_environment(repository):
    root, cache = repository
    unknown = cache.parent / "my-notes.txt"
    unknown.write_text("user notes", encoding="utf-8")
    for directory in (".venv", "dist", "releases", "build", "backups"):
        (root / directory).mkdir()
        (root / directory / "keep.txt").write_text("keep", encoding="utf-8")
    manifest, report = clean.run_cleanup(root)
    assert report["mode"] == "dry-run"
    assert len(report["candidates"]) == 1
    assert cache.exists() and unknown.read_text() == "user notes"
    assert json.loads(manifest.read_text(encoding="utf-8"))["outcomes"] == []
    assert len(list(root.glob("*/keep.txt"))) == 5


def test_cleanup_apply_saves_plan_first_and_preserves_unknown(repository, monkeypatch):
    root, cache = repository
    unknown = cache.parent / "not-generated.pyc"
    unknown.write_text("user data", encoding="utf-8")
    original = clean.apply_plan

    def inspect_before_delete(root, plan):
        manifests = list((root / "work/cleanup").glob("*.json"))
        assert manifests and cache.exists()
        assert json.loads(manifests[0].read_text(encoding="utf-8"))["candidates"][0]["sha256"]
        return original(root, plan)

    monkeypatch.setattr(clean, "apply_plan", inspect_before_delete)
    _, report = clean.run_cleanup(root, apply=True)
    assert report["outcomes"][0]["status"] == "deleted"
    assert not cache.exists() and unknown.exists()
    assert (root / "src/sample.py").exists()


@pytest.mark.parametrize("change", ["tracked", "modified", "hardlink"])
def test_cleanup_revalidates_file_after_plan(repository, change):
    root, cache = repository
    plan = clean.plan_cleanup(root)
    if change == "tracked":
        git(root, "add", "-f", str(cache))
    elif change == "modified":
        cache.write_bytes(cache.read_bytes() + b"changed")
    else:
        os.link(cache, root / "user-copy.pyc")
    result = clean.apply_plan(root, plan)
    assert result[0]["status"] == "retained" and cache.exists()


def make_directory_link(link, target):
    if os.name == "nt":
        # Structured environment variables avoid shell interpolation of paths.
        env = {**os.environ, "ZFE_TEST_LINK": str(link), "ZFE_TEST_TARGET": str(target)}
        subprocess.run([
            "powershell.exe", "-NoProfile", "-Command",
            "$ErrorActionPreference='Stop'; "
            "New-Item -ItemType Junction -Path $env:ZFE_TEST_LINK -Target $env:ZFE_TEST_TARGET | Out-Null",
        ], env=env, check=True, capture_output=True)
    else:
        link.symlink_to(target, target_is_directory=True)


@pytest.mark.parametrize("location", ["src/linked", "src/__pycache__/nested", "work"])
def test_cleanup_rejects_junctions_in_scan_and_manifest(repository, location):
    root, cache = repository
    outside = root.parent / "outside"
    outside.mkdir()
    sentinel = outside / "precious.txt"
    sentinel.write_text("preserve", encoding="utf-8")
    link = root / location
    make_directory_link(link, outside)
    try:
        if location == "work":
            with pytest.raises(ValueError, match="reparse"):
                clean.run_cleanup(root, apply=True)
            assert cache.exists()
        else:
            _, plan = clean.run_cleanup(root, apply=True)
            assert any(entry["path"] == location for entry in plan["retained"])
        assert sentinel.read_text() == "preserve"
    finally:
        # Remove the link itself, never recurse into its target.
        if os.name == "nt":
            link.rmdir()
        else:
            link.unlink()


def test_cleanup_rejects_parent_link_and_path_traversal(repository):
    root, cache = repository
    link = root.parent / "alias"
    make_directory_link(link, root)
    try:
        with pytest.raises(ValueError, match="reparse"):
            clean.checked_path(link, link / "src/sample.py")
        with pytest.raises(ValueError, match="boundary"):
            clean.checked_path(root, root / "../outside.txt")
        forged = {"candidates": [{"path": "src/../../outside.txt"}]}
        assert clean.apply_plan(root, forged)[0]["status"] == "retained"
        assert cache.exists()
    finally:
        if os.name == "nt":
            link.rmdir()
        else:
            link.unlink()


def test_docs_reports_broken_links_anchors_and_references(tmp_path):
    target = tmp_path / "topic.md"
    target.write_text("# 中文 heading\n\n# 中文 heading\n", encoding="utf-8")
    page = tmp_path / "README.md"
    page.write_text(
        "[ok](topic.md#中文-heading-1)\n[bad](topic.md#missing)\n"
        "[missing](lost.md)\n[ref][unknown]\n"
        "```markdown\n[example](not-real.md)\n```\n", encoding="utf-8"
    )
    count, errors = docs.check_file(tmp_path, page)
    assert count == 3 and len(errors) == 3
    assert any("missing anchor" in e for e in errors)
    assert any("undefined reference" in e for e in errors)
    assert not any("not-real" in e for e in errors)


def test_publication_includes_new_source_respects_deletions_and_ignores_cache(repository):
    root, cache = repository
    (root / "docs").mkdir()
    (root / "docs/README.md").write_text("# Public documentation", encoding="utf-8")
    deleted = root / "src/old.py"
    deleted.write_text("old = True", encoding="utf-8")
    git(root, "add", "src/old.py")
    deleted.unlink()
    report = publication.audit_repository(root)
    assert not report["errors"]
    names = {entry["path"] for entry in report["files"]}
    assert names == {".gitignore", "src/sample.py", "docs/README.md"}
    assert cache.exists()
    assert all(len(entry["sha256"]) == 64 for entry in report["files"])


@pytest.mark.parametrize("name", [".env", "dist/installer.exe", "docs/paper.pdf", "src/index.sqlite3"])
def test_publication_rejects_runtime_and_private_files(repository, name):
    root, _ = repository
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"synthetic publication rejection fixture")
    report = publication.audit_repository(root)
    assert any(name in error for error in report["errors"])
    assert path.exists()


def test_publication_rejects_personal_paths(repository):
    root, _ = repository
    (root / "src/private_path.txt").write_text(str(Path.home()), encoding="utf-8")
    report = publication.audit_repository(root)
    assert any("Personal home path" in error for error in report["errors"])


def test_publication_rejects_link_ancestors(repository, monkeypatch):
    root, _ = repository
    outside = root.parent / "external"
    outside.mkdir()
    (outside / "README.md").write_text("keep external data", encoding="utf-8")
    link = root / "src/alias"
    make_directory_link(link, outside)
    monkeypatch.setattr(publication, "git_names", lambda root, *args:
                        set() if "-ci" in args else {"src/alias/README.md"})
    try:
        report = publication.audit_repository(root)
        assert any("reparse" in error for error in report["errors"])
        assert not report["files"]
    finally:
        link.rmdir() if os.name == "nt" else link.unlink()
