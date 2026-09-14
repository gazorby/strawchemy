"""Generate the VitePress reference pages from the strawchemy source tree."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, get_args

import griffe
from cyclopts import App
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


class ReferenceGenerationError(StrawchemyError):
    """Raised when an emitter cannot produce a complete set of reference pages."""


@dataclass(frozen=True)
class Page:
    """One generated markdown file."""

    path: str
    title: str
    content: str


@dataclass(frozen=True)
class ApiPageSpec:
    """One API page and the exported names it documents."""

    path: str
    title: str
    exports: tuple[str, ...]


@dataclass(frozen=True)
class ConfigClassSpec:
    """One configuration class, addressed by its path inside the loaded package."""

    griffe_path: str
    title: str


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
    api_pages: tuple[ApiPageSpec, ...]
    config_classes: tuple[ConfigClassSpec, ...]
    operator_exports: tuple[str, ...]

    @property
    def documented_exports(self) -> set[str]:
        """Every export name claimed by some page."""
        return {name for page in self.api_pages for name in page.exports} | set(self.operator_exports)


@dataclass(frozen=True)
class MarkdownRenderer:
    """Render griffe objects as the markdown blocks a reference page is built from."""

    source_url: str
    version: str

    def _signature(self, func: griffe.Function) -> str:
        parts: list[str] = []
        for parameter in func.parameters:
            if parameter.name == "self":
                continue
            text = parameter.name
            if parameter.annotation is not None:
                text = f"{text}: {parameter.annotation}"
            if parameter.default is not None:
                text = f"{text} = {parameter.default}"
            parts.append(text)
        returns = f" -> {func.returns}" if func.returns is not None else ""
        return f"{func.name}({', '.join(parts)}){returns}"

    def _parameter_descriptions(self, func: griffe.Function) -> dict[str, str]:
        if func.docstring is None:
            return {}
        descriptions: dict[str, str] = {}
        for section in func.docstring.parsed:
            if section.kind is griffe.DocstringSectionKind.parameters:
                for parameter in section.value:
                    # Variadic entries keep their stars in the docstring but not in the signature.
                    descriptions[parameter.name.lstrip("*")] = parameter.description.replace("\n", " ").strip()
        return descriptions

    def _parameters_table(self, func: griffe.Function) -> str:
        descriptions = self._parameter_descriptions(func)
        rows = ["| Parameter | Type | Default | Description |", "| --- | --- | --- | --- |"]
        documented = False
        for parameter in func.parameters:
            if parameter.name == "self":
                continue
            documented = True
            description = descriptions.get(parameter.name, "").replace("|", r"\|")
            rows.append(
                f"| `{parameter.name}` | {self.cell(parameter.annotation)} | {self.cell(parameter.default)} | "
                f"{description} |"
            )
        return "\n".join(rows) if documented else ""

    def _render_function(self, func: griffe.Function, level: int) -> str:
        blocks = [
            f"{'#' * level} `{self._signature(func)}`",
            self.source_link(func),
            self.docstring_text(func),
            self._parameters_table(func),
        ]
        return "\n\n".join(block for block in blocks if block)

    def _public_methods(self, cls: griffe.Class) -> list[griffe.Function]:
        methods = [
            resolved
            for name, member in cls.members.items()
            if not name.startswith("_") and isinstance(resolved := self.resolve(member), griffe.Function)
        ]
        return sorted(methods, key=lambda method: method.name)

    def resolve(self, obj: griffe.Object | griffe.Alias) -> griffe.Object:
        """Follow an alias to the object it stands for."""
        return obj.final_target if isinstance(obj, griffe.Alias) else obj

    def cell(self, value: object) -> str:
        """Render a value as a table cell, escaping the pipes a union annotation contains."""
        return f"`{value}`".replace("|", r"\|") if value is not None else ""

    def source_link(self, obj: griffe.Object | griffe.Alias) -> str:
        """Link to the object's definition line, pinned to the documented version."""
        return f"[source]({self.source_url}/v{self.version}/{obj.relative_filepath}#L{obj.lineno})"

    def docstring_text(self, obj: griffe.Object | griffe.Alias) -> str:
        """Join the prose sections of an object's docstring, dropping the structured ones."""
        if obj.docstring is None:
            return ""
        return "\n".join(
            section.value for section in obj.docstring.parsed if section.kind is griffe.DocstringSectionKind.text
        )

    def attributes(self, cls: griffe.Object | griffe.Alias) -> list[tuple[str, griffe.Attribute]]:
        """List the public attributes of a class, sorted by name."""
        return [
            (name, attribute)
            for name, member in sorted(self.resolve(cls).members.items())
            if not name.startswith("_") and isinstance(attribute := self.resolve(member), griffe.Attribute)
        ]

    def is_read_only(self, attribute: griffe.Attribute) -> bool:
        """Report whether a user can set the attribute when constructing the class."""
        # A property has no setter here, and `field(init=False)` is populated in __post_init__.
        return "property" in attribute.labels or (attribute.value is not None and "init=False" in str(attribute.value))

    def description(self, attribute: griffe.Attribute) -> str:
        """Render an attribute's docstring as a single table cell."""
        return self.docstring_text(attribute).replace("\n", " ").replace("|", r"\|").strip()

    def render_object(self, obj: griffe.Object | griffe.Alias) -> str:
        """Render a section documenting one exported name."""
        target = self.resolve(obj)
        blocks = [f"### {obj.name}", self.source_link(target), self.docstring_text(target)]
        if isinstance(target, griffe.Function):
            blocks.append(self._parameters_table(target))
        elif isinstance(target, griffe.Attribute) and target.annotation is not None:
            blocks.append(f"```python\n{obj.name}: {target.annotation}\n```")
        elif isinstance(target, griffe.Class):
            blocks.extend(self._render_function(method, level=4) for method in self._public_methods(target))
        return "\n\n".join(block for block in blocks if block)


@dataclass(frozen=True)
class ApiEmitter:
    """Emit one page per API page spec."""

    package: griffe.Module
    renderer: MarkdownRenderer
    header: str
    specs: tuple[ApiPageSpec, ...]

    def emit(self) -> list[Page]:
        """Render one page per spec, in declaration order.

        Raises:
            ReferenceGenerationError: If an exported name cannot be resolved by griffe.
        """
        pages: list[Page] = []
        for spec in self.specs:
            sections = [self.header, f"# {spec.title}"]
            for name in spec.exports:
                obj = self.package[name]
                if obj is None:
                    msg = f"`{name}` is exported but griffe could not resolve it."
                    raise ReferenceGenerationError(msg)
                sections.append(self.renderer.render_object(obj))
            pages.append(Page(path=spec.path, title=spec.title, content="\n\n".join(sections) + "\n"))
        return pages


@dataclass(frozen=True)
class ConfigEmitter:
    """Emit the single options page covering every configuration class."""

    package: griffe.Module
    renderer: MarkdownRenderer
    header: str
    specs: tuple[ConfigClassSpec, ...]

    def options_table(self, cls: griffe.Object | griffe.Alias) -> str:
        """Tabulate the public attributes of a configuration class.

        Raises:
            ReferenceGenerationError: If the class exposes no attribute to tabulate.
        """
        rows = ["| Option | Type | Default | Description |", "| --- | --- | --- | --- |"]
        documented = False
        for name, attribute in self.renderer.attributes(cls):
            if self.renderer.is_read_only(attribute):
                continue
            documented = True
            rows.append(
                f"| `{name}` | {self.renderer.cell(attribute.annotation)} | "
                f"{self.renderer.cell(attribute.value)} | {self.renderer.description(attribute)} |"
            )
        if not documented:
            msg = f"`{self.renderer.resolve(cls).name}` exposes no settable attributes; remove its spec."
            raise ReferenceGenerationError(msg)
        return "\n".join(rows)

    def read_only_table(self, cls: griffe.Object | griffe.Alias) -> str:
        """Tabulate the attributes a user cannot set, or return an empty string when there are none."""
        rows = ["| Attribute | Type | Description |", "| --- | --- | --- |"]
        documented = False
        for name, attribute in self.renderer.attributes(cls):
            if not self.renderer.is_read_only(attribute):
                continue
            documented = True
            rows.append(
                f"| `{name}` | {self.renderer.cell(attribute.annotation)} | {self.renderer.description(attribute)} |"
            )
        return "\n".join(rows) if documented else ""

    def emit(self) -> list[Page]:
        """Render the options page covering every configuration class."""
        sections = [self.header, "# Configuration options"]
        for spec in self.specs:
            cls = self.renderer.resolve(self.package[spec.griffe_path])
            read_only = self.read_only_table(cls)
            sections.extend(
                block
                for block in (
                    f"## {spec.title}",
                    self.renderer.source_link(cls),
                    self.renderer.docstring_text(cls),
                    self.options_table(cls),
                    "### Read-only attributes" if read_only else "",
                    read_only,
                )
                if block
            )
        return [Page(path="reference/config", title="Configuration options", content="\n\n".join(sections) + "\n")]


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
        renderer = MarkdownRenderer(self.spec.layout.source_url, package_version())
        header = self.spec.layout.header
        return (
            ApiEmitter(package, renderer, header, self.spec.api_pages),
            ConfigEmitter(package, renderer, header, self.spec.config_classes),
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
                f"Add each name to an api page or to the operator exports in {Path(__file__).name}."
            )
            raise ReferenceGenerationError(msg)

    def generate(self) -> list[Page]:
        """Build every reference page, without touching the filesystem."""
        package = self.load_package()
        self.check_exports_covered(package)
        return [page for emitter in self._emitters(package) for page in emitter.emit()]


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
    api_pages=(
        ApiPageSpec("reference/api/mapper", "Mapper", ("Strawchemy", "ModelInstance")),
        ApiPageSpec(
            "reference/api/config",
            "Configuration types",
            ("StrawchemyConfig", "FieldGroup", "ALL", "RELATIONSHIPS", "SCALARS"),
        ),
        ApiPageSpec(
            "reference/api/repositories",
            "Repositories",
            ("StrawchemyAsyncRepository", "StrawchemySyncRepository"),
        ),
        ApiPageSpec(
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
        ApiPageSpec(
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
        ApiPageSpec("reference/api/hooks", "Hooks", ("QueryHook",)),
        ApiPageSpec("reference/api/errors", "Errors", ("ErrorType", "InputValidationError")),
    ),
    config_classes=(
        ConfigClassSpec("StrawchemyConfig", "StrawchemyConfig"),
        ConfigClassSpec("dto.types.DTOConfig", "DTOConfig"),
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
