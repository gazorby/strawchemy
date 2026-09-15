"""Generate the VitePress reference pages from the strawchemy source tree."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, get_args

import griffe
from cyclopts import App
from griffe2md import ConfigDict, render_object_docs
from testapp.schema import schema

from strawchemy import typing as strawchemy_typing
from strawchemy.__metadata__ import __version__
from strawchemy.exceptions import StrawchemyError

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence


class Emitter(Protocol):
    """One family of reference pages."""

    def emit(self) -> list[Page]:
        """Render the pages this emitter owns."""
        ...


REPO_ROOT = Path(__file__).resolve().parent.parent

_HEADING = re.compile(r"^(#{2,6}) `([A-Za-z_][\w.]*)`$", re.MULTILINE)
_CROSSREF = re.compile(r"\[([^\]]*)\]\(#([^)]*)\)")
_ANCHOR = re.compile(r"\{#([^}]+)\}")

RENDER_CONFIG: ConfigDict = {
    "docstring_style": "google",
    "show_root_heading": True,
    "show_root_full_path": True,
    "show_root_members_full_path": True,
    "show_object_full_path": True,
    "summary": False,
    "show_bases": False,
    "separate_signature": True,
    "show_signature_annotations": True,
    "signature_crossrefs": False,
    "docstring_section_style": "table",
    "filters": ["!^_"],
    "show_if_no_docstring": True,
}


class ReferenceGenerationError(StrawchemyError):
    """Raised when an emitter cannot produce a complete set of reference pages."""


@dataclass(frozen=True)
class Page:
    """One generated markdown file."""

    path: str
    title: str
    content: str


@dataclass(frozen=True)
class PageSpec:
    """One generated page and the objects it documents, addressed inside the loaded package."""

    path: str
    title: str
    objects: tuple[str, ...]
    heading_level: int = 2


@dataclass(frozen=True)
class SiteLayout:
    """The site-wide strings a page needs to place itself."""

    header: str
    source_url: str
    sidebar_groups: Mapping[str, str]


@dataclass(frozen=True)
class ReferenceSpec:
    """Everything the generator needs to know about what to document."""

    repo_root: Path
    layout: SiteLayout
    pages: tuple[PageSpec, ...]
    operator_exports: tuple[str, ...]

    @property
    def documented_exports(self) -> set[str]:
        """Every name claimed by some page."""
        return {name for page in self.pages for name in page.objects} | set(self.operator_exports)


@dataclass(frozen=True)
class GriffeRenderer:
    """Render griffe objects through griffe2md, anchored the way VitePress addresses headings."""

    source_url: str
    version: str

    def source_link(self, obj: griffe.Object | griffe.Alias) -> str:
        """Link to the object's definition line, pinned to the documented version."""
        return f"[source]({self.source_url}/v{self.version}/{obj.relative_filepath}#L{obj.lineno})"

    def render(self, obj: griffe.Object | griffe.Alias, heading_level: int) -> str:
        """Render one object as the markdown section a reference page is built from."""
        target = obj.final_target if isinstance(obj, griffe.Alias) else obj
        markdown = render_object_docs(target, config=RENDER_CONFIG | {"heading_level": heading_level})
        return insert_source_link(anchor_headings(markdown), self.source_link(target))


def anchor_id(path: str) -> str:
    """Render a dotted object path as an anchor safe in a url fragment and a css selector."""
    return path.replace(".", "-")


def anchor_headings(markdown: str) -> str:
    """Shorten every heading to the object's own name, anchored by its full path."""

    def replace_heading(match: re.Match[str]) -> str:
        hashes, path = match.groups()
        return f"{hashes} `{path.rsplit('.', 1)[-1]}` {{#{anchor_id(path)}}}"

    return _HEADING.sub(replace_heading, markdown)


def insert_source_link(markdown: str, link: str) -> str:
    """Place the source link between the heading griffe2md opens with and the body."""
    heading, _, body = markdown.partition("\n")
    return f"{heading}\n\n{link}\n{body}"


def resolve_crossrefs(pages: Sequence[Page]) -> list[Page]:
    """Point every reference at the page documenting it, dropping the ones no page documents.

    Raises:
        ReferenceGenerationError: If two pages define the same anchor.
    """
    anchors: dict[str, str] = {}
    for page in pages:
        for anchor in _ANCHOR.findall(page.content):
            if anchor in anchors and anchors[anchor] != page.path:
                msg = f"`{anchor}` is claimed by both `{anchors[anchor]}` and `{page.path}`."
                raise ReferenceGenerationError(msg)
            anchors[anchor] = page.path

    def resolve_page(page: Page) -> Page:
        def replace_crossref(match: re.Match[str]) -> str:
            text, target = match.groups()
            anchor = anchor_id(target)
            path = anchors.get(anchor)
            if path is None:
                return text
            return f"[{text}](#{anchor})" if path == page.path else f"[{text}](/{path}#{anchor})"

        return replace(page, content=_CROSSREF.sub(replace_crossref, page.content))

    return [resolve_page(page) for page in pages]


@dataclass(frozen=True)
class ObjectPageEmitter:
    """Emit one page per page specification."""

    package: griffe.Module
    renderer: GriffeRenderer
    header: str
    specs: tuple[PageSpec, ...]

    def emit(self) -> list[Page]:
        """Render one page per spec, in declaration order.

        Raises:
            ReferenceGenerationError: If a documented object cannot be resolved by griffe.
        """
        pages: list[Page] = []
        for spec in self.specs:
            sections = [self.header, f"# {spec.title}"]
            for path in spec.objects:
                try:
                    obj = self.package[path]
                except KeyError as error:
                    msg = f"`{path}` is documented but griffe could not resolve it."
                    raise ReferenceGenerationError(msg) from error
                sections.append(self.renderer.render(obj, spec.heading_level))
            pages.append(Page(path=spec.path, title=spec.title, content="\n\n".join(sections) + "\n"))
        return pages


@dataclass(frozen=True)
class GraphQLEmitter:
    """Emit the operator matrix and the example application's schema."""

    header: str
    operator_exports: tuple[str, ...]

    def literal_values(self, alias: object) -> tuple[str, ...]:
        """Collect the string literals a type alias admits, flattening the aliases it unions."""
        values: set[str] = set()
        for argument in get_args(alias):
            if isinstance(argument, str):
                values.add(argument)
            else:
                values.update(self.literal_values(argument))
        return tuple(sorted(values))

    def emit(self) -> list[Page]:
        """Render the operator matrix and the example application's schema.

        Raises:
            ReferenceGenerationError: If an operator alias admits no literal.
        """
        by_alias = {name: self.literal_values(getattr(strawchemy_typing, name)) for name in self.operator_exports}
        if empty := sorted(name for name, values in by_alias.items() if not values):
            msg = f"No operators resolved for: {', '.join(empty)}."
            raise ReferenceGenerationError(msg)

        rows = ["| Operator | Comparison types |", "| --- | --- |"]
        for operator in sorted({value for values in by_alias.values() for value in values}):
            carriers = sorted(name for name, values in by_alias.items() if operator in values)
            rows.append(f"| `{operator}` | {', '.join(f'`{name}`' for name in carriers)} |")

        matrix = Page(
            path="reference/graphql/operators",
            title="Operators",
            content="\n\n".join(
                [
                    self.header,
                    "# Operators",
                    "Every filter operator, and the comparison type aliases that expose it.",
                    "\n".join(rows),
                ]
            )
            + "\n",
        )
        example = Page(
            path="reference/graphql/example-schema",
            title="Example schema",
            content="\n\n".join(
                [
                    self.header,
                    "# Example schema",
                    "The full GraphQL schema generated for the example application in `examples/testapp`.",
                    f"```graphql\n{schema}\n```",
                ]
            )
            + "\n",
        )
        return [matrix, example]


@dataclass(frozen=True)
class ReferenceGenerator:
    """Build every reference page a specification describes."""

    spec: ReferenceSpec

    def _emitters(self, package: griffe.Module) -> tuple[Emitter, ...]:
        renderer = GriffeRenderer(self.spec.layout.source_url, package_version())
        header = self.spec.layout.header
        return (
            ObjectPageEmitter(package, renderer, header, self.spec.pages),
            GraphQLEmitter(header, self.spec.operator_exports),
        )

    def load_package(self) -> griffe.Module:
        """Load `strawchemy` statically, leaving `TYPE_CHECKING` names as annotation text.

        Raises:
            ReferenceGenerationError: If griffe resolves the package to something other than a module.
        """
        package = griffe.load(
            "strawchemy",
            search_paths=[self.spec.repo_root / "src"],
            resolve_aliases=True,
            allow_inspection=False,
            docstring_parser="google",
        )
        if not isinstance(package, griffe.Module):
            msg = f"Expected `strawchemy` to load as a module, got {type(package).__name__}."
            raise ReferenceGenerationError(msg)
        return package

    def check_exports_covered(self, package: griffe.Module) -> None:
        """Fail when a public export belongs to no reference page.

        Raises:
            ReferenceGenerationError: If any name in `__all__` is undocumented.
        """
        missing = sorted({str(name) for name in package.exports or ()} - self.spec.documented_exports)
        if missing:
            msg = (
                f"Exports missing from the reference: {', '.join(missing)}. "
                f"Add each name to a page spec or to the operator exports in {Path(__file__).name}."
            )
            raise ReferenceGenerationError(msg)

    def generate(self) -> list[Page]:
        """Build every reference page, without touching the filesystem."""
        package = self.load_package()
        self.check_exports_covered(package)
        pages = [page for emitter in self._emitters(package) for page in emitter.emit()]
        return resolve_crossrefs(pages)


@dataclass(frozen=True)
class SiteWriter:
    """Write generated pages and the sidebar the VitePress config imports."""

    output_root: Path
    layout: SiteLayout

    def sidebar_entries(self, pages: Sequence[Page]) -> list[dict[str, object]]:
        """Group pages into the VitePress sidebar structure the site config imports."""
        grouped: dict[str, list[Page]] = {}
        for page in pages:
            parent = page.path.rsplit("/", 1)[0]
            grouped.setdefault(self.layout.sidebar_groups.get(parent, "Reference"), []).append(page)
        return [
            {
                "text": group,
                "collapsed": False,
                "items": [
                    {"text": page.title, "link": f"/{page.path}"}
                    for page in sorted(grouped[group], key=lambda page: page.title)
                ],
            }
            for group in sorted(grouped)
        ]

    def write_pages(self, pages: Sequence[Page]) -> None:
        """Write each page under the output root, creating parent directories as needed."""
        for page in pages:
            destination = self.output_root / f"{page.path}.md"
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(page.content, encoding="utf-8")

    def write_sidebar(self, pages: Sequence[Page]) -> None:
        """Write the generated sidebar next to the VitePress config."""
        destination = self.output_root / ".vitepress" / "reference-sidebar.json"
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(self.sidebar_entries(pages), indent=2) + "\n", encoding="utf-8")


DEFAULT_SPEC = ReferenceSpec(
    repo_root=REPO_ROOT,
    layout=SiteLayout(
        header="<!-- generated by tools/docs_reference.py — do not edit -->",
        source_url="https://github.com/gazorby/strawchemy/blob",
        sidebar_groups={
            "reference/api": "API",
            "reference/graphql": "GraphQL",
            "reference": "Reference",
        },
    ),
    pages=(
        PageSpec("reference/api/mapper", "Mapper", ("Strawchemy", "ModelInstance")),
        PageSpec(
            "reference/api/config",
            "Field groups",
            ("FieldGroup", "ALL", "RELATIONSHIPS", "SCALARS"),
        ),
        PageSpec(
            "reference/api/repositories",
            "Repositories",
            ("StrawchemyAsyncRepository", "StrawchemySyncRepository"),
        ),
        PageSpec(
            "reference/api/comparisons",
            "Comparisons",
            (
                "GraphQLComparison",
                "ArrayComparison",
                "DateComparison",
                "DateTimeComparison",
                "EqualityComparison",
                "OrderComparison",
                "TextComparison",
                "TimeComparison",
                "TimeDeltaComparison",
            ),
        ),
        PageSpec(
            "reference/api/mutation-inputs",
            "Mutation inputs",
            (
                "Input",
                "RequiredToManyUpdateInput",
                "RequiredToOneInput",
                "ToManyCreateInput",
                "ToManyUpdateInput",
                "ToOneInput",
                "ValidationErrorType",
            ),
        ),
        PageSpec("reference/api/hooks", "Hooks", ("QueryHook",)),
        PageSpec("reference/api/errors", "Errors", ("ErrorType", "InputValidationError")),
        PageSpec("reference/config", "Configuration options", ("StrawchemyConfig", "dto.types.DTOConfig")),
    ),
    operator_exports=(
        "ArrayOperator",
        "ComparisonOperator",
        "DateOperator",
        "DateTimeOperator",
        "EqualityOperator",
        "OrderOperator",
        "TextOperator",
        "TimeDeltaOperator",
        "TimeOperator",
    ),
)

app = App(name="docs-reference", help=__doc__)


def package_version() -> str:
    """Return the installed strawchemy version, used to pin source permalinks."""
    return __version__


@app.default
def generate(output: Path = DEFAULT_SPEC.repo_root / "docs") -> None:
    """Generate the reference pages into the given directory."""
    pages = ReferenceGenerator(DEFAULT_SPEC).generate()
    writer = SiteWriter(output, DEFAULT_SPEC.layout)
    writer.write_pages(pages)
    writer.write_sidebar(pages)
    print(f"Wrote {len(pages)} reference pages to {output}")


if __name__ == "__main__":
    app()
