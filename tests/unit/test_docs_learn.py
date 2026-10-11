from __future__ import annotations

import json
from pathlib import Path
from typing import TypedDict

import pytest


class _SidebarItem(TypedDict, total=False):
    link: str
    items: list[_SidebarItem]


_DOCS = Path(__file__).parents[2] / "docs" / "src"
_NAVIGATION = Path(__file__).parents[2] / "docs" / ".vitepress" / "navigation.json"
_LEARN_PAGES = sorted((_DOCS / "learn").rglob("*.md"))


def _page_url(page: Path) -> str:
    relative = page.relative_to(_DOCS).with_suffix("")
    return f"/{relative.parent}/" if relative.name == "index" else f"/{relative}"


def _links(items: list[_SidebarItem]) -> set[str]:
    links = {item["link"] for item in items if "link" in item}
    for item in items:
        links |= _links(item.get("items", []))
    return links


@pytest.mark.parametrize("page", _LEARN_PAGES, ids=lambda page: page.stem)
def test_code_is_always_visible(page: Path) -> None:
    """Learn snippets are never collapsed behind a disclosure widget."""
    content = page.read_text()
    assert "<details>" not in content
    assert "<summary>" not in content


@pytest.mark.parametrize("page", _LEARN_PAGES, ids=lambda page: page.stem)
def test_page_is_reachable_from_the_sidebar(page: Path) -> None:
    """Every learn page has a sidebar entry, so none is orphaned."""
    sidebar = json.loads(_NAVIGATION.read_text())["sidebar"]["/learn/"]
    assert _page_url(page) in _links(sidebar)
