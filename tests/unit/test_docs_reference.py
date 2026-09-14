from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from types import ModuleType

    import griffe
    from tools.docs_reference import ConfigEmitter, GraphQLEmitter, MarkdownRenderer, ReferenceGenerator

REPO_ROOT = Path(__file__).resolve().parents[2]
VERSION = "0.0.1"


@pytest.fixture(scope="module")
def docs_reference() -> ModuleType:
    """Import `tools/docs_reference.py`, which lives outside any package."""
    path = REPO_ROOT / "tools" / "docs_reference.py"
    spec = importlib.util.spec_from_file_location("docs_reference", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def generator(docs_reference: ModuleType) -> ReferenceGenerator:
    """A generator driven by the specification the command line uses."""
    return docs_reference.ReferenceGenerator(docs_reference.DEFAULT_SPEC)


@pytest.fixture
def package(generator: ReferenceGenerator) -> griffe.Module:
    """A private copy of the documented package, so a test may mutate it."""
    return generator.load_package()


@pytest.fixture
def renderer(docs_reference: ModuleType) -> MarkdownRenderer:
    """A renderer pinned to a fixed version, so source links stay stable across releases."""
    return docs_reference.MarkdownRenderer(docs_reference.DEFAULT_SPEC.layout.source_url, VERSION)


@pytest.fixture
def api_pages(docs_reference: ModuleType, package: griffe.Module, renderer: MarkdownRenderer) -> dict[str, str]:
    """The rendered api pages, keyed by path and in declaration order."""
    spec = docs_reference.DEFAULT_SPEC
    emitter = docs_reference.ApiEmitter(package, renderer, spec.layout.header, spec.api_pages)
    return {page.path: page.content for page in emitter.emit()}


@pytest.fixture
def config_emitter(docs_reference: ModuleType, package: griffe.Module, renderer: MarkdownRenderer) -> ConfigEmitter:
    """An emitter for the options page of the documented configuration classes."""
    spec = docs_reference.DEFAULT_SPEC
    return docs_reference.ConfigEmitter(package, renderer, spec.layout.header, spec.config_classes)


@pytest.fixture
def graphql_emitter(docs_reference: ModuleType) -> GraphQLEmitter:
    """An emitter for the operator matrix and the example schema."""
    spec = docs_reference.DEFAULT_SPEC
    return docs_reference.GraphQLEmitter(spec.layout.header, spec.operator_exports)


def test_every_export_is_covered_by_a_page(generator: ReferenceGenerator, package: griffe.Module) -> None:
    """Test that every name in `__all__` is claimed by a reference page."""
    generator.check_exports_covered(package)


def test_uncovered_export_is_reported(
    docs_reference: ModuleType, generator: ReferenceGenerator, package: griffe.Module
) -> None:
    """Test that an export belonging to no page names itself in the error."""
    package.exports = [*(package.exports or ()), "NotDocumentedAnywhere"]
    with pytest.raises(docs_reference.ReferenceGenerationError, match="NotDocumentedAnywhere"):
        generator.check_exports_covered(package)


def test_spec_claims_the_exports_of_all_its_pages(docs_reference: ModuleType) -> None:
    """Test that a specification claims the names of its api pages and of its operator aliases, and no others."""
    spec = docs_reference.ReferenceSpec(
        repo_root=REPO_ROOT,
        layout=docs_reference.DEFAULT_SPEC.layout,
        api_pages=(docs_reference.ApiPageSpec("reference/api/mapper", "Mapper", ("Strawchemy",)),),
        config_classes=(),
        operator_exports=("EqualityOperator",),
    )
    assert spec.documented_exports == {"Strawchemy", "EqualityOperator"}


def test_generate_is_deterministic(generator: ReferenceGenerator) -> None:
    """Test that two consecutive runs produce identical pages."""
    first = generator.generate()
    second = generator.generate()
    assert [(page.path, page.content) for page in first] == [(page.path, page.content) for page in second]


def test_api_pages_cover_every_group(docs_reference: ModuleType, api_pages: dict[str, str]) -> None:
    """Test that one page is emitted per api page specification, in declaration order."""
    assert list(api_pages) == [spec.path for spec in docs_reference.DEFAULT_SPEC.api_pages]


def test_api_page_documents_each_symbol_with_a_source_link(api_pages: dict[str, str]) -> None:
    """Test that a documented symbol carries a version-pinned link to its source line."""
    mapper = api_pages["reference/api/mapper"]
    assert "### Strawchemy" in mapper
    assert f"blob/v{VERSION}/src/strawchemy/mapper.py#L" in mapper


def test_api_page_documents_public_methods(api_pages: dict[str, str]) -> None:
    """Test that a documented class renders a section per public method."""
    mapper = api_pages["reference/api/mapper"]
    for method in ("create", "delete", "field", "filter_field", "update", "update_by_ids", "upsert"):
        assert f"#### `{method}" in mapper, method


def test_parameters_table_escapes_pipes_in_annotations(api_pages: dict[str, str]) -> None:
    """Test that a union annotation does not split its table row into extra cells."""
    row = next(line for line in api_pages["reference/api/mapper"].splitlines() if line.startswith("| `resolver`"))
    assert len(re.findall(r"(?<!\\)\|", row)) == 5
    assert r"Any \| None" in row


def test_parameters_table_documents_variadic_parameters(api_pages: dict[str, str]) -> None:
    """Test that a `**kwargs` parameter keeps the description its docstring entry gives it."""
    row = next(line for line in api_pages["reference/api/mapper"].splitlines() if line.startswith("| `field_kwargs`"))
    assert "strawberry.field" in row


def test_generate_produces_no_empty_pages(docs_reference: ModuleType, generator: ReferenceGenerator) -> None:
    """Test that no emitted page consists of only the generated-file header."""
    pages = generator.generate()
    assert pages
    for page in pages:
        assert page.content.strip() != docs_reference.DEFAULT_SPEC.layout.header, page.path


def test_config_page_tabulates_every_documented_field(config_emitter: ConfigEmitter) -> None:
    """Test that each config class renders a row per documented attribute under its own heading."""
    (page,) = config_emitter.emit()
    row = "| `auto_snake_case` | `bool` | `True` | Automatically convert snake cased names to camel case |"
    assert page.path == "reference/config"
    assert row in page.content
    assert "## StrawchemyConfig" in page.content
    assert "## DTOConfig" in page.content


def test_options_table_escapes_pipes_in_annotations(config_emitter: ConfigEmitter) -> None:
    """Test that a union-typed option does not split its table row into extra cells."""
    (page,) = config_emitter.emit()
    row = next(line for line in page.content.splitlines() if line.startswith("| `filter_overrides`"))
    assert len(re.findall(r"(?<!\\)\|", row)) == 5
    assert r"FilterMap \| None" in row


def test_options_table_rejects_a_class_with_no_fields(
    docs_reference: ModuleType, config_emitter: ConfigEmitter, package: griffe.Module
) -> None:
    """Test that a class exposing no attributes names itself in the error."""
    with pytest.raises(docs_reference.ReferenceGenerationError, match="QueryHookError"):
        config_emitter.options_table(package["exceptions.QueryHookError"])


def test_options_table_omits_non_settable_attributes(config_emitter: ConfigEmitter, package: griffe.Module) -> None:
    """Test that properties and `init=False` fields stay out of the settable options table."""
    table = config_emitter.options_table(package["StrawchemyConfig"])
    for name in ("field_config", "order_config", "pagination_config", "distinct_on_config", "inspector"):
        assert f"| `{name}` |" not in table, name
    assert "| `auto_snake_case` |" in table


def test_read_only_table_lists_non_settable_attributes(config_emitter: ConfigEmitter, package: griffe.Module) -> None:
    """Test that properties and `init=False` fields are tabulated separately, without a default."""
    table = config_emitter.read_only_table(package["StrawchemyConfig"])
    assert table.startswith("| Attribute | Type | Description |")
    for name in ("field_config", "inspector"):
        assert f"| `{name}` |" in table, name
    assert "| `auto_snake_case` |" not in table


def test_read_only_table_is_empty_without_non_settable_attributes(
    config_emitter: ConfigEmitter, package: griffe.Module
) -> None:
    """Test that a class whose attributes are all settable renders no read-only table."""
    assert config_emitter.read_only_table(package["dto.base.PurposeConfig"]) == ""


def test_config_page_separates_read_only_attributes(config_emitter: ConfigEmitter) -> None:
    """Test that the options page gives non-settable attributes their own subsection."""
    (page,) = config_emitter.emit()
    assert "### Read-only attributes" in page.content


def test_literal_values_flattens_nested_unions(graphql_emitter: GraphQLEmitter) -> None:
    """Test that an alias built on another alias reports both vocabularies, sorted."""
    from strawchemy.typing import EqualityOperator, OrderOperator

    assert graphql_emitter.literal_values(EqualityOperator) == ("eq", "in", "is_null", "neq", "nin")
    equality = set(graphql_emitter.literal_values(EqualityOperator))
    assert equality < set(graphql_emitter.literal_values(OrderOperator))


def test_graphql_pages_are_emitted(graphql_emitter: GraphQLEmitter) -> None:
    """Test that the GraphQL emitter produces the operator matrix and the example schema."""
    pages = {page.path: page.content for page in graphql_emitter.emit()}
    assert set(pages) == {"reference/graphql/operators", "reference/graphql/example-schema"}


def test_operator_matrix_maps_operators_to_comparison_aliases(graphql_emitter: GraphQLEmitter) -> None:
    """Test that each operator row lists the aliases exposing it, one cell per column."""
    pages = {page.path: page.content for page in graphql_emitter.emit()}
    matrix = pages["reference/graphql/operators"]
    row = next(line for line in matrix.splitlines() if line.startswith("| `eq`"))
    assert len(re.findall(r"(?<!\\)\|", row)) == 3
    assert "EqualityOperator" in row
    assert "| `overlap` |" in matrix


def test_example_schema_page_contains_sdl(graphql_emitter: GraphQLEmitter) -> None:
    """Test that the example application's schema is rendered as a GraphQL code block."""
    pages = {page.path: page.content for page in graphql_emitter.emit()}
    sdl = pages["reference/graphql/example-schema"]
    assert "```graphql" in sdl
    assert "type Query {" in sdl


def test_sidebar_groups_pages_by_directory(
    docs_reference: ModuleType, generator: ReferenceGenerator, tmp_path: Path
) -> None:
    """Test that sidebar groups are ordered and link every generated page."""
    writer = docs_reference.SiteWriter(tmp_path, docs_reference.DEFAULT_SPEC.layout)
    entries = writer.sidebar_entries(generator.generate())
    texts = [entry["text"] for entry in entries]
    assert texts == sorted(texts)
    links = {item["link"] for entry in entries for item in entry["items"]}
    assert "/reference/api/mapper" in links
    assert "/reference/graphql/operators" in links
    assert "/reference/config" in links


def test_command_writes_pages_and_sidebar(docs_reference: ModuleType, tmp_path: Path) -> None:
    """Test that a run writes every page plus the sidebar the VitePress config imports, then exits successfully."""
    with pytest.raises(SystemExit) as exit_info:
        docs_reference.app(["--output", str(tmp_path)])
    assert exit_info.value.code == 0
    assert (tmp_path / "reference" / "api" / "mapper.md").is_file()
    assert (tmp_path / "reference" / "config.md").is_file()
    assert (tmp_path / "reference" / "graphql" / "operators.md").is_file()
    assert (tmp_path / ".vitepress" / "reference-sidebar.json").is_file()
