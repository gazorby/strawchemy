from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from types import ModuleType

REPO_ROOT = Path(__file__).resolve().parents[2]
NAVIGATION = {"nav": [{"text": "Learn", "link": "/learn/"}], "sidebar": {"/learn/": [{"text": "Intro"}]}}
REFERENCE_SIDEBAR = [{"text": "API", "items": [{"text": "Mapper", "link": "/reference/api/mapper"}]}]


@pytest.fixture(scope="module")
def docs_snapshot() -> ModuleType:
    """Import `tools/docs_snapshot.py`, which lives outside any package."""
    path = REPO_ROOT / "tools" / "docs_snapshot.py"
    spec = importlib.util.spec_from_file_location("docs_snapshot", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def docs(tmp_path: Path) -> Path:
    """A docs tree with a page, a changelog including the repository one, and both navigation files."""
    root = tmp_path / "repo" / "docs"
    (root / "src" / "learn").mkdir(parents=True)
    (root / ".vitepress").mkdir()
    (root / "src" / "index.md").write_text("# Home\n")
    (root / "src" / "learn" / "index.md").write_text("# Learn\n")
    (root / "src" / "changelog.md").write_text("<!--@include: ../../CHANGELOG.md-->\n")
    (root.parent / "CHANGELOG.md").write_text("## v0.25.0\n")
    (root / ".vitepress" / "navigation.json").write_text(json.dumps(NAVIGATION))
    (root / ".vitepress" / "reference-sidebar.json").write_text(json.dumps(REFERENCE_SIDEBAR))
    return root


@pytest.mark.parametrize("version", ["v1.0", "0.25.0", "v0.25.0rc1", "dev"])
def test_check_version_rejects(docs_snapshot: ModuleType, version: str) -> None:
    """Test that anything but a vX.Y.Z release is refused."""
    with pytest.raises(ValueError, match=version):
        docs_snapshot.check_version(version)


def test_check_version_accepts_release(docs_snapshot: ModuleType) -> None:
    """Test that a vX.Y.Z release is accepted."""
    docs_snapshot.check_version("v0.25.0")


def test_merged_navigation_adds_reference_sidebar(docs_snapshot: ModuleType) -> None:
    """Test that the reference sidebar joins the navigation without mutating the input."""
    navigation = json.loads(json.dumps(NAVIGATION))
    merged = docs_snapshot.merged_navigation(navigation, REFERENCE_SIDEBAR)
    assert merged["sidebar"] == {"/learn/": [{"text": "Intro"}], "/reference/": REFERENCE_SIDEBAR}
    assert merged["nav"] == NAVIGATION["nav"]
    assert navigation == NAVIGATION


def test_expand_includes_inlines_file(docs_snapshot: ModuleType, tmp_path: Path) -> None:
    """Test that an include directive is replaced by the content of the file it names."""
    (tmp_path / "part.md").write_text("included\n")
    assert docs_snapshot.expand_includes("before\n<!--@include: ./part.md-->\nafter\n", tmp_path) == (
        "before\nincluded\n\nafter\n"
    )


def test_expand_includes_leaves_plain_text(docs_snapshot: ModuleType, tmp_path: Path) -> None:
    """Test that markdown without include directives is returned unchanged."""
    assert docs_snapshot.expand_includes("# Title\n<!-- comment -->\n", tmp_path) == "# Title\n<!-- comment -->\n"


def test_snapshot_writes_folder(docs_snapshot: ModuleType, docs: Path, tmp_path: Path) -> None:
    """Test that a snapshot copies the pages, inlines includes and merges the navigation."""
    folder = docs_snapshot.snapshot("v0.25.0", tmp_path / "archive", docs=docs)
    assert folder == tmp_path / "archive" / "v0.25.0"
    assert (folder / "index.md").read_text() == "# Home\n"
    assert (folder / "learn" / "index.md").read_text() == "# Learn\n"
    assert (folder / "changelog.md").read_text() == "## v0.25.0\n\n"
    assert json.loads((folder / "navigation.json").read_text()) == {
        "nav": NAVIGATION["nav"],
        "sidebar": {"/learn/": [{"text": "Intro"}], "/reference/": REFERENCE_SIDEBAR},
    }


def test_version_links_prefixes_absolute_links(docs_snapshot: ModuleType) -> None:
    """Test that site-absolute markdown links move under the version, and other links stay."""
    text = "[a](/learn/x) [b](https://example.com/y) [c](./z) [d](#anchor) [e](//cdn.example.com/f)\n"
    assert docs_snapshot.version_links(text, "v0.25.0") == (
        "[a](/v0.25.0/learn/x) [b](https://example.com/y) [c](./z) [d](#anchor) [e](//cdn.example.com/f)\n"
    )


def test_snapshot_keeps_page_links_in_version(docs_snapshot: ModuleType, docs: Path, tmp_path: Path) -> None:
    """Test that an archived page links to pages of its own version."""
    (docs / "src" / "learn" / "index.md").write_text("See [filtering](/learn/filtering).\n")
    folder = docs_snapshot.snapshot("v0.25.0", tmp_path / "archive", docs=docs)
    assert (folder / "learn" / "index.md").read_text() == "See [filtering](/v0.25.0/learn/filtering).\n"


def test_snapshot_refuses_existing_folder(docs_snapshot: ModuleType, docs: Path, tmp_path: Path) -> None:
    """Test that an existing snapshot is never overwritten."""
    (tmp_path / "archive" / "v0.25.0").mkdir(parents=True)
    with pytest.raises(FileExistsError):
        docs_snapshot.snapshot("v0.25.0", tmp_path / "archive", docs=docs)


def test_failed_snapshot_leaves_no_folder(docs_snapshot: ModuleType, docs: Path, tmp_path: Path) -> None:
    """Test that a snapshot failing midway leaves the archive untouched, so a retry can succeed."""
    (docs.parent / "CHANGELOG.md").unlink()
    with pytest.raises(FileNotFoundError):
        docs_snapshot.snapshot("v0.25.0", tmp_path / "archive", docs=docs)
    assert list((tmp_path / "archive").iterdir()) == []
