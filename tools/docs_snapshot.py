"""Freeze the documentation of a release into the archive the site serves under /vX.Y.Z/."""

from __future__ import annotations

import json
import re
import shutil
import tempfile
from pathlib import Path

from cyclopts import App

REPO_ROOT = Path(__file__).resolve().parent.parent
RELEASE = re.compile(r"^v\d+\.\d+\.\d+$")

_INCLUDE = re.compile(r"<!--\s*@include:\s*(.+?)\s*-->")
_ABSOLUTE_LINK = re.compile(r"\]\(/(?!/)")

app = App(name="docs-snapshot", help=__doc__)


def check_version(version: str) -> None:
    """Validate that the version names a release.

    Raises:
        ValueError: If the version is not shaped vX.Y.Z.
    """
    if not RELEASE.match(version):
        msg = f"Not a release version: {version}"
        raise ValueError(msg)


def merged_navigation(navigation: dict[str, object], reference_sidebar: list[object]) -> dict[str, object]:
    """Return the navigation with the generated reference sidebar added under /reference/."""
    sidebar = navigation.get("sidebar", {})
    assert isinstance(sidebar, dict)
    return navigation | {"sidebar": sidebar | {"/reference/": reference_sidebar}}


def expand_includes(text: str, base: Path) -> str:
    """Replace each VitePress include directive by the content of the file it names, relative to base."""
    return _INCLUDE.sub(lambda match: (base / match.group(1)).read_text(encoding="utf-8"), text)


def version_links(text: str, version: str) -> str:
    """Move site-absolute markdown links under /version/, so an archived page links within its version."""
    return _ABSOLUTE_LINK.sub(f"](/{version}/", text)


@app.default
def snapshot(version: str, output: Path = REPO_ROOT / "docs" / "archive", *, docs: Path = REPO_ROOT / "docs") -> Path:
    """Copy the current documentation into output/version, self-contained.

    Raises:
        FileExistsError: If output/version already exists.
    """
    check_version(version)
    folder = output / version
    if folder.exists():
        msg = f"Snapshot already exists: {folder}"
        raise FileExistsError(msg)
    source = docs / "src"
    output.mkdir(parents=True, exist_ok=True)
    # Built aside and moved in last, so a failure never leaves a partial folder that blocks the retry.
    with tempfile.TemporaryDirectory(dir=output) as staging:
        draft = Path(staging) / version
        shutil.copytree(source, draft)
        for page in draft.rglob("*.md"):
            origin = source / page.relative_to(draft)
            text = expand_includes(page.read_text(encoding="utf-8"), origin.parent)
            page.write_text(version_links(text, version), encoding="utf-8")
        navigation = json.loads((docs / ".vitepress" / "navigation.json").read_text(encoding="utf-8"))
        reference_sidebar = json.loads((docs / ".vitepress" / "reference-sidebar.json").read_text(encoding="utf-8"))
        (draft / "navigation.json").write_text(
            json.dumps(merged_navigation(navigation, reference_sidebar), indent=2) + "\n", encoding="utf-8"
        )
        draft.rename(folder)
    print(f"Wrote {folder}")
    return folder


if __name__ == "__main__":
    app()
