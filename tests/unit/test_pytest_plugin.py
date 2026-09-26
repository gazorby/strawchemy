from __future__ import annotations

from typing import Any

import pytest

_PYTEST_ARGS = "-p no:pretty"  # pretty plugin makes pytester unable to parse pytest output


@pytest.fixture(autouse=True)
def fx_pyproject(pytester: pytest.Pytester) -> None:
    pytester.makepyprojecttoml(
        """
        [tool.pytest.ini_options]
        asyncio_mode = "auto"
        asyncio_default_fixture_loop_scope = "function"
        """
    )


@pytest.mark.parametrize(
    ("query"),
    [
        pytest.param("{ fruits { name sweetness } }", id="basic"),
        pytest.param("{ fruits { name color { id name } } }", id="relation"),
    ],
)
def test_patch_query_fixture(query: str, pytester: pytest.Pytester) -> None:
    pytester.makepyfile(
        f"""
        import pytest
        import strawberry
        from strawchemy import Strawchemy, StrawchemyAsyncRepository, StrawchemySyncRepository, StrawchemyConfig
        from strawchemy.testing import MockContext
        from tests.unit.models import Fruit, SQLDataTypes
        from typing import Any
        from datetime import timedelta
        from strawberry.scalars import JSON
        from strawberry.schema.types.scalar import DEFAULT_SCALAR_REGISTRY
        from strawchemy.schema.scalars import Interval

        SCALAR_OVERRIDES: dict[object, Any] = {{dict[str, Any]: DEFAULT_SCALAR_REGISTRY[JSON], timedelta: Interval}}
        pytest_plugins = ["strawchemy.testing.pytest_plugin", "pytest_asyncio"]

        strawchemy = Strawchemy("postgresql")

        @strawchemy.type(Fruit, include="all")
        class FruitType:
            ...

        @strawchemy.type(SQLDataTypes, include="all")
        class DataTypes:
            ...

        @strawberry.type
        class QueryAsync:
            fruits: list[FruitType] = strawchemy.field(repository_type=StrawchemyAsyncRepository)
            data_types: list[DataTypes] = strawchemy.field(repository_type=StrawchemyAsyncRepository)

        @strawberry.type
        class QuerySync:
            fruits: list[FruitType] = strawchemy.field(repository_type=StrawchemySyncRepository)
            data_types: list[DataTypes] = strawchemy.field(repository_type=StrawchemySyncRepository)

        async def test_async(context: MockContext) -> None:
            schema = strawberry.Schema(query=QueryAsync, scalar_overrides=SCALAR_OVERRIDES)
            result = await schema.execute("{query}", context_value=context)
            assert result.errors is None
            assert result.data is not None

        def test_sync(context: MockContext) -> None:
            schema = strawberry.Schema(query=QuerySync, scalar_overrides=SCALAR_OVERRIDES)
            result = schema.execute_sync("{query}", context_value=context)
            assert result.errors is None
            assert result.data is not None
        """
    )

    result = pytester.runpytest(_PYTEST_ARGS)
    result.assert_outcomes(passed=2)


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        pytest.param(
            '"{ fruitsAggregate { aggregations { count } } }"',
            {"fruitsAggregate": {"aggregations": {"count": 0}}},
            id="root-aggregations",
        ),
        pytest.param(
            '"{ colors { fruitsAggregate { count } } }"',
            {"colors": [{"fruitsAggregate": {"count": 0}}]},
            id="child-aggregate-list",
        ),
        pytest.param(
            "'{ color(id: \"84552ccd-efad-4561-ac72-23ec5c5c2cf9\") { fruitsAggregate { count } } }'",
            {"color": {"fruitsAggregate": {"count": 0}}},
            id="child-aggregate-one",
        ),
    ],
)
def test_computed_values(query: str, expected: str, pytester: pytest.Pytester) -> None:
    pytester.makepyfile(
        f"""
        import pytest
        import strawberry
        from strawchemy import Strawchemy, StrawchemyConfig
        from strawchemy.testing import MockContext
        from tests.unit.models import Fruit, Color

        pytest_plugins = ["strawchemy.testing.pytest_plugin"]

        strawchemy = Strawchemy("postgresql")

        @strawchemy.aggregate(Fruit, include="all")
        class FruitAggregateType:
            pass

        @strawchemy.type(Color, include="all", override=True)
        class ColorType:
            pass

        @strawberry.type
        class Query:
            fruits_aggregate: FruitAggregateType = strawchemy.field(root_aggregations=True)
            colors: list[ColorType] = strawchemy.field()
            color: ColorType = strawchemy.field()

        def test(context: MockContext) -> None:
            schema = strawberry.Schema(query=Query)
            result = schema.execute_sync({query}, context_value=context)
            assert result.errors is None
            assert result.data is not None

            assert result.data == {expected}
        """
    )

    result = pytester.runpytest(_PYTEST_ARGS)
    result.assert_outcomes(passed=1)


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        pytest.param(
            '"{ fruitsAggregate { aggregations { count } } }"',
            {"fruitsAggregate": {"aggregations": {"count": 2}}},
            id="root-aggregations",
        ),
        pytest.param(
            '"{ colors { fruitsAggregate { count } } }"',
            {"colors": [{"fruitsAggregate": {"count": 2}}]},
            id="child-aggregate-list",
        ),
        pytest.param(
            "'{ color(id: \"84552ccd-efad-4561-ac72-23ec5c5c2cf9\") { fruitsAggregate { count } } }'",
            {"color": {"fruitsAggregate": {"count": 2}}},
            id="child-aggregate-one",
        ),
    ],
)
def test_custom_computed_values(query: str, expected: Any, pytester: pytest.Pytester) -> None:
    pytester.makepyfile(
        f"""
        from __future__ import annotations
        from typing import Any
        import pytest
        import strawberry
        from strawchemy import Strawchemy, StrawchemyConfig
        from strawchemy.testing import MockContext
        from tests.unit.models import Fruit, Color

        pytest_plugins = ["strawchemy.testing.pytest_plugin"]

        strawchemy = Strawchemy("postgresql")

        @strawchemy.aggregate(Fruit, include="all")
        class FruitAggregateType:
            pass

        @strawchemy.type(Color, include="all", override=True)
        class ColorType:
            pass

        @strawberry.type
        class Query:
            fruits_aggregate: FruitAggregateType = strawchemy.field(root_aggregations=True)
            colors: list[ColorType] = strawchemy.field()
            color: ColorType = strawchemy.field()

        @pytest.fixture
        def computed_values() -> dict[str, Any]:
            return {{"count": 2}}

        def test(context: MockContext) -> None:
            schema = strawberry.Schema(query=Query)
            result = schema.execute_sync({query}, context_value=context)
            assert result.errors is None
            assert result.data is not None

            assert result.data == {expected}
        """
    )

    result = pytester.runpytest(_PYTEST_ARGS)
    result.assert_outcomes(passed=1)


_NESTED_RELATIONS_MODULE = """
from __future__ import annotations
from typing import Any
from uuid import UUID
import pytest
import strawberry
from strawchemy import Strawchemy, StrawchemyAsyncRepository, StrawchemyConfig, StrawchemySyncRepository
from strawchemy.testing import MockContext
from tests.unit.models import Fruit, Color

pytest_plugins = ["strawchemy.testing.pytest_plugin", "pytest_asyncio"]

strawchemy = Strawchemy(StrawchemyConfig("postgresql", pagination="all"))

@strawchemy.type(Fruit, include="all")
class FruitType:
    pass

@strawchemy.type(Color, include="all", override=True)
class ColorType:
    pass

@strawberry.type
class QueryAsync:
    fruits: list[FruitType] = strawchemy.field(repository_type=StrawchemyAsyncRepository)
    colors: list[ColorType] = strawchemy.field(repository_type=StrawchemyAsyncRepository)

@strawberry.type
class QuerySync:
    fruits: list[FruitType] = strawchemy.field(repository_type=StrawchemySyncRepository)
    colors: list[ColorType] = strawchemy.field(repository_type=StrawchemySyncRepository)

{fixtures}

async def test_async(context: MockContext) -> None:
    result = await strawberry.Schema(query=QueryAsync).execute({query!r}, context_value=context)
    assert result.errors is None
    {data_assertion}

def test_sync(context: MockContext) -> None:
    result = strawberry.Schema(query=QuerySync).execute_sync({query!r}, context_value=context)
    assert result.errors is None
    {data_assertion}
"""

_INSTANCE_GRAPH_FIXTURE = """
@pytest.fixture
def model_instance() -> Any:
    red = Color(id=UUID("84552ccd-efad-4561-ac72-23ec5c5c2cf9"), name="red")
    apple = Fruit(name="apple", sweetness=1, color=red)
    Fruit(name="cherry", sweetness=2, color=red)
    return {root}
"""

_COMPUTED_VALUES_FIXTURE = """
@pytest.fixture
def computed_values() -> dict[str, Any]:
    return {values!r}
"""


def _nested_relations_module(
    query: str, expected: object, root: str | None, computed_values: dict[str, Any] | None = None
) -> str:
    fixtures = [_INSTANCE_GRAPH_FIXTURE.format(root=root)] if root is not None else []
    if computed_values is not None:
        fixtures.append(_COMPUTED_VALUES_FIXTURE.format(values=computed_values))
    return _NESTED_RELATIONS_MODULE.format(
        fixtures="\n".join(fixtures), query=query, data_assertion=f"assert result.data == {expected!r}"
    )


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        pytest.param(
            "{ fruits { color { fruitsAggregate { count } } } }",
            {"fruits": [{"color": {"fruitsAggregate": {"count": 0}}}]},
            id="to-one-aggregate",
        ),
        pytest.param(
            "{ colors { fruits { color { fruitsAggregate { count } } } } }",
            {"colors": [{"fruits": [{"color": {"fruitsAggregate": {"count": 0}}}]}]},
            id="to-many-to-one-aggregate",
        ),
        pytest.param(
            "{ colors { fruits { fruitsAggregate: color { fruitsAggregate { count } } } } }",
            {"colors": [{"fruits": [{"fruitsAggregate": {"fruitsAggregate": {"count": 0}}}]}]},
            id="aliased-to-one-aggregate",
        ),
    ],
)
def test_nested_computed_values_default_instance(query: str, expected: Any, pytester: pytest.Pytester) -> None:
    pytester.makepyfile(_nested_relations_module(query, expected, root=None))

    result = pytester.runpytest(_PYTEST_ARGS)
    result.assert_outcomes(passed=2)


@pytest.mark.parametrize(
    "query",
    [
        pytest.param("{ colors { fruits { name } } }", id="to-many"),
        pytest.param("{ colors { fruits { name color { name } } } }", id="to-many-to-one"),
    ],
)
def test_nested_relations_default_instance(query: str, pytester: pytest.Pytester) -> None:
    pytester.makepyfile(
        _NESTED_RELATIONS_MODULE.format(fixtures="", query=query, data_assertion="assert result.data is not None")
    )

    result = pytester.runpytest(_PYTEST_ARGS)
    result.assert_outcomes(passed=2)


@pytest.mark.parametrize(
    ("query", "root", "expected", "computed_values"),
    [
        pytest.param(
            "{ fruits { name color { name } } }",
            "apple",
            {"fruits": [{"name": "apple", "color": {"name": "red"}}]},
            None,
            id="to-one",
        ),
        pytest.param(
            "{ colors { name fruits { name } } }",
            "red",
            {"colors": [{"name": "red", "fruits": [{"name": "apple"}, {"name": "cherry"}]}]},
            None,
            id="to-many",
        ),
        pytest.param(
            "{ colors { fruits { name color { name } } } }",
            "red",
            {
                "colors": [
                    {
                        "fruits": [
                            {"name": "apple", "color": {"name": "red"}},
                            {"name": "cherry", "color": {"name": "red"}},
                        ]
                    }
                ]
            },
            None,
            id="two-levels",
        ),
        pytest.param(
            "{ colors { first: fruits(limit: 1) { name } all: fruits(offset: 0) { sweetness } } }",
            "red",
            {
                "colors": [
                    {"first": [{"name": "apple"}, {"name": "cherry"}], "all": [{"sweetness": 1}, {"sweetness": 2}]}
                ]
            },
            None,
            id="aliased-relations-with-arguments",
        ),
        pytest.param(
            "{ fruits { name color { name fruitsAggregate { count } } } }",
            "apple",
            {"fruits": [{"name": "apple", "color": {"name": "red", "fruitsAggregate": {"count": 0}}}]},
            None,
            id="to-one-aggregate",
        ),
        pytest.param(
            "{ colors { fruits { name color { fruitsAggregate { count } } } } }",
            "red",
            {
                "colors": [
                    {
                        "fruits": [
                            {"name": "apple", "color": {"fruitsAggregate": {"count": 0}}},
                            {"name": "cherry", "color": {"fruitsAggregate": {"count": 0}}},
                        ]
                    }
                ]
            },
            None,
            id="two-levels-aggregate",
        ),
        pytest.param(
            "{ fruits { color { fruitsAggregate { count } } } }",
            "apple",
            {"fruits": [{"color": {"fruitsAggregate": {"count": 2}}}]},
            {"count": 2},
            id="to-one-custom-aggregate",
        ),
        pytest.param(
            "{ colors { fruits { color { fruitsAggregate { count } } } } }",
            "red",
            {
                "colors": [
                    {
                        "fruits": [
                            {"color": {"fruitsAggregate": {"count": 2}}},
                            {"color": {"fruitsAggregate": {"count": 2}}},
                        ]
                    }
                ]
            },
            {"count": 2},
            id="two-levels-custom-aggregate",
        ),
    ],
)
def test_nested_relations_instance_graph(
    query: str, root: str, expected: Any, computed_values: dict[str, Any] | None, pytester: pytest.Pytester
) -> None:
    pytester.makepyfile(_nested_relations_module(query, expected, root, computed_values))

    result = pytester.runpytest(_PYTEST_ARGS)
    result.assert_outcomes(passed=2)


def test_keyed_dict_relation(pytester: pytest.Pytester) -> None:
    pytester.makepyfile(
        """
        from __future__ import annotations
        from typing import Any
        import pytest
        import strawberry
        from sqlalchemy import ForeignKey
        from sqlalchemy.orm import DeclarativeBase, Mapped, attribute_keyed_dict, mapped_column, relationship
        from strawchemy import Strawchemy
        from strawchemy.testing import MockContext

        pytest_plugins = ["strawchemy.testing.pytest_plugin"]

        class Base(DeclarativeBase):
            pass

        class Basket(Base):
            __tablename__ = "basket"
            id: Mapped[int] = mapped_column(primary_key=True)
            items: Mapped[dict[str, Item]] = relationship(collection_class=attribute_keyed_dict("name"))

        class Item(Base):
            __tablename__ = "item"
            id: Mapped[int] = mapped_column(primary_key=True)
            name: Mapped[str]
            basket_id: Mapped[int] = mapped_column(ForeignKey("basket.id"))

        strawchemy = Strawchemy("postgresql")

        @strawchemy.type(Item, include="all")
        class ItemType:
            pass

        @strawchemy.type(Basket, include="all")
        class BasketType:
            pass

        @strawberry.type
        class Query:
            baskets: list[BasketType] = strawchemy.field()

        @pytest.fixture
        def model_instance() -> Any:
            return Basket(id=1, items={"apple": Item(id=1, name="apple"), "pear": Item(id=2, name="pear")})

        def test(context: MockContext) -> None:
            result = strawberry.Schema(query=Query).execute_sync("{ baskets { items { name } } }", context_value=context)
            assert result.errors is None
            assert result.data == {"baskets": [{"items": [{"name": "apple"}, {"name": "pear"}]}]}
        """
    )

    result = pytester.runpytest(_PYTEST_ARGS)
    result.assert_outcomes(passed=1)


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        pytest.param(
            "{ customers { discount maximum account { amount } } }",
            {"customers": [{"discount": 5, "maximum": 10, "account": {"amount": 3}}]},
            id="plain-fields",
        ),
        pytest.param(
            "{ customers { accountsAggregate { count } } }",
            {"customers": [{"accountsAggregate": {"count": 0}}]},
            id="aggregate-count",
        ),
    ],
)
def test_fields_named_like_aggregation_functions(query: str, expected: object, pytester: pytest.Pytester) -> None:
    pytester.makepyfile(
        f"""
        from __future__ import annotations
        from typing import Any
        import pytest
        import strawberry
        from sqlalchemy import ForeignKey
        from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
        from strawchemy import Strawchemy
        from strawchemy.testing import MockContext

        pytest_plugins = ["strawchemy.testing.pytest_plugin"]

        class Base(DeclarativeBase):
            pass

        class Customer(Base):
            __tablename__ = "customer"
            id: Mapped[int] = mapped_column(primary_key=True)
            discount: Mapped[int]
            maximum: Mapped[int]
            account_id: Mapped[int] = mapped_column(ForeignKey("account.id"))
            account: Mapped[Account] = relationship(foreign_keys=[account_id])
            accounts: Mapped[list[Account]] = relationship(foreign_keys="Account.customer_id")

        class Account(Base):
            __tablename__ = "account"
            id: Mapped[int] = mapped_column(primary_key=True)
            amount: Mapped[int]
            customer_id: Mapped[int | None] = mapped_column(ForeignKey("customer.id"))

        strawchemy = Strawchemy("postgresql")

        @strawchemy.type(Account, include="all")
        class AccountType:
            pass

        @strawchemy.type(Customer, include="all")
        class CustomerType:
            pass

        @strawberry.type
        class Query:
            customers: list[CustomerType] = strawchemy.field()

        @pytest.fixture
        def model_instance() -> Any:
            return Customer(id=1, discount=5, maximum=10, account=Account(id=1, amount=3))

        def test(context: MockContext) -> None:
            result = strawberry.Schema(query=Query).execute_sync({query!r}, context_value=context)
            assert result.errors is None
            assert result.data == {expected!r}
        """
    )

    result = pytester.runpytest(_PYTEST_ARGS)
    result.assert_outcomes(passed=1)


@pytest.mark.parametrize(
    ("query", "root", "expected", "computed_values"),
    [
        pytest.param(
            "{ colors { fruitsAggregate { max { sweetness name } } } }",
            None,
            {"colors": [{"fruitsAggregate": {"max": {"sweetness": None, "name": None}}}]},
            None,
            id="function-with-arguments-default-instance",
        ),
        pytest.param(
            "{ colors { fruitsAggregate { max { sweetness } } } }",
            "red",
            {"colors": [{"fruitsAggregate": {"max": {"sweetness": None}}}]},
            None,
            id="function-with-arguments-default",
        ),
        pytest.param(
            "{ colors { fruitsAggregate { max { sweetness } min { sweetness } } } }",
            "red",
            {"colors": [{"fruitsAggregate": {"max": {"sweetness": 3}, "min": {"sweetness": 1}}}]},
            {"max.sweetness": 3, "fruitsAggregate.min.sweetness": 1},
            id="function-with-arguments-by-path",
        ),
        pytest.param(
            "{ colors { fruitsAggregate { max { sweetness } min { sweetness } } } }",
            "red",
            {"colors": [{"fruitsAggregate": {"max": {"sweetness": 3}, "min": {"sweetness": 3}}}]},
            {"sweetness": 3},
            id="function-with-arguments-by-name",
        ),
        pytest.param(
            "{ colors { fruitsAggregate { count } fruits { color { fruitsAggregate { count } } } } }",
            "red",
            {
                "colors": [
                    {
                        "fruitsAggregate": {"count": 1},
                        "fruits": [
                            {"color": {"fruitsAggregate": {"count": 5}}},
                            {"color": {"fruitsAggregate": {"count": 5}}},
                        ],
                    }
                ]
            },
            {"count": 1, "fruits.color.fruitsAggregate.count": 5},
            id="count-by-path",
        ),
        pytest.param(
            "{ colors { fruitsAggregate { count } fruits { color { total: fruitsAggregate { count } } } } }",
            "red",
            {
                "colors": [
                    {
                        "fruitsAggregate": {"count": 0},
                        "fruits": [{"color": {"total": {"count": 4}}}, {"color": {"total": {"count": 4}}}],
                    }
                ]
            },
            {"total.count": 4},
            id="count-by-aliased-path",
        ),
        pytest.param(
            "{ colors { fruits { color { total: fruitsAggregate { count } } } } }",
            "red",
            {"colors": [{"fruits": [{"color": {"total": {"count": 4}}}, {"color": {"total": {"count": 4}}}]}]},
            {"fruitsAggregate.count": 4},
            id="count-by-field-name-of-aliased-path",
        ),
        pytest.param(
            "{ colors { fruitsAggregate { count } fruits { color { fruitsAggregate { count } } } } }",
            "red",
            {
                "colors": [
                    {
                        "fruitsAggregate": {"count": 7},
                        "fruits": [
                            {"color": {"fruitsAggregate": {"count": 0}}},
                            {"color": {"fruitsAggregate": {"count": 0}}},
                        ],
                    }
                ]
            },
            {"colors.fruitsAggregate.count": 7},
            id="count-by-path-from-root-field",
        ),
        pytest.param(
            "{ all: colors { fruitsAggregate { count } } }",
            "red",
            {"all": [{"fruitsAggregate": {"count": 7}}]},
            {"all.fruitsAggregate.count": 7},
            id="count-by-path-from-aliased-root-field",
        ),
    ],
)
def test_nested_computed_values_by_path(
    query: str, root: str | None, expected: object, computed_values: dict[str, Any] | None, pytester: pytest.Pytester
) -> None:
    pytester.makepyfile(_nested_relations_module(query, expected, root, computed_values))

    result = pytester.runpytest(_PYTEST_ARGS)
    result.assert_outcomes(passed=2)


@pytest.mark.parametrize(
    ("query", "computed_values", "expected"),
    [
        pytest.param(
            "{ fruitsAggregate { aggregations { count max { sweetness } } } }",
            {},
            {"fruitsAggregate": {"aggregations": {"count": 0, "max": {"sweetness": None}}}},
            id="default",
        ),
        pytest.param(
            "{ fruitsAggregate { aggregations { count max { sweetness } } } }",
            {"fruitsAggregate.aggregations.count": 3, "max.sweetness": 9},
            {"fruitsAggregate": {"aggregations": {"count": 3, "max": {"sweetness": 9}}}},
            id="by-path",
        ),
    ],
)
def test_root_aggregations_by_path(
    query: str, computed_values: dict[str, Any], expected: object, pytester: pytest.Pytester
) -> None:
    pytester.makepyfile(
        f"""
        from __future__ import annotations
        from typing import Any
        import pytest
        import strawberry
        from strawchemy import Strawchemy
        from strawchemy.testing import MockContext
        from tests.unit.models import Fruit

        pytest_plugins = ["strawchemy.testing.pytest_plugin"]

        strawchemy = Strawchemy("postgresql")

        @strawchemy.aggregate(Fruit, include="all")
        class FruitAggregateType:
            pass

        @strawberry.type
        class Query:
            fruits_aggregate: FruitAggregateType = strawchemy.field(root_aggregations=True)

        @pytest.fixture
        def computed_values() -> dict[str, Any]:
            return {computed_values!r}

        def test(context: MockContext) -> None:
            result = strawberry.Schema(query=Query).execute_sync({query!r}, context_value=context)
            assert result.errors is None
            assert result.data == {expected!r}
        """
    )

    result = pytester.runpytest(_PYTEST_ARGS)
    result.assert_outcomes(passed=1)
