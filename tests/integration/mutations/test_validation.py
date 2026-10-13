from __future__ import annotations

from typing import TYPE_CHECKING, Annotated

import pytest
import strawberry
from pydantic import AfterValidator
from sqlalchemy import Insert, insert

from strawchemy import Input, InputValidationError, StrawchemyAsyncRepository, ValidationErrorType
from strawchemy.validation.pydantic import PydanticValidation
from tests.integration.fixtures import Operations, QueryTracker, SchemaTypes
from tests.integration.models import Color, Fruit, RankedUser
from tests.integration.typing import RawRecordData
from tests.integration.utils import data_argument, to_graphql_representation
from tests.typing import AnyQueryExecutor
from tests.utils import maybe_async

if TYPE_CHECKING:
    from syrupy.assertion import SnapshotAssertion

    from strawchemy import Strawchemy
    from strawchemy.typing import SupportedDialect

pytestmark = [pytest.mark.integration]

_COLORS: RawRecordData = [{"id": 1, "name": "Red"}]


def _check_lower_case(value: str) -> str:
    if not value.islower():
        msg = "Name must be lower cased"
        raise ValueError(msg)
    return value


def _schema(strawchemy: Strawchemy) -> Operations:
    @strawchemy.type(Fruit, include=["name", "farms", "product"], scope="schema")
    class FruitType: ...

    @strawchemy.type(Color, include=["id", "name", "fruits"], scope="schema")
    class ColorType: ...

    # Generated primary keys are optional on create inputs, nested ones included, only under include="all".
    @strawchemy.create_input(Color, include="all")
    class ColorCreateInput: ...

    # Nested fruits not declared here are dropped from the validated input before the insert.
    @strawchemy.pydantic.create(Color, include=["name", "fruits"])
    class ColorCreateValidation:
        name: Annotated[str, AfterValidator(_check_lower_case)]

    @strawchemy.pk_update_input(Color, include=["id", "name"])
    class ColorUpdateInput: ...

    @strawchemy.pydantic.pk_update(Color, include=["id", "name"])
    class ColorPkUpdateValidation: ...

    @strawchemy.type(RankedUser, include=["name", "rank"])
    class RankedUserType: ...

    @strawchemy.create_input(RankedUser, include=["name"])
    class RankedUserCreateInput: ...

    @strawchemy.pydantic.create(RankedUser, include=["name"])
    class RankedUserCreateValidation:
        name: Annotated[str, AfterValidator(_check_lower_case)]

    # No case reads through it; a schema needs a query type.
    @strawberry.type
    class Query:
        colors: list[ColorType] = strawchemy.field()

    # Cases run the custom resolvers below on async sessions only.
    @strawberry.type
    class Mutation:
        create_color: ColorType = strawchemy.create(ColorCreateInput)
        create_validated_color: ColorType | ValidationErrorType = strawchemy.create(
            ColorCreateInput, validation=PydanticValidation(ColorCreateValidation)
        )
        update_color: ColorType = strawchemy.update_by_ids(ColorUpdateInput)
        update_validated_color: ColorType | ValidationErrorType = strawchemy.update_by_ids(
            ColorUpdateInput, validation=PydanticValidation(ColorPkUpdateValidation)
        )

        @strawchemy.field(graphql_type=ColorType | ValidationErrorType, arguments=data_argument(ColorCreateInput))
        async def create_color_manual_validation(
            self, info: strawberry.Info, data: ColorCreateInput
        ) -> ColorType | ValidationErrorType:
            try:
                return (
                    await StrawchemyAsyncRepository(ColorType, info).create(
                        Input(data, PydanticValidation(ColorCreateValidation))
                    )
                ).graphql_type()
            except InputValidationError as error:
                return error.graphql_type()

        @strawchemy.field(
            graphql_type=RankedUserType | ValidationErrorType, arguments=data_argument(RankedUserCreateInput)
        )
        async def create_validated_ranked_user(
            self, info: strawberry.Info, data: RankedUserCreateInput
        ) -> RankedUserType | ValidationErrorType:
            try:
                user_input = Input(data, PydanticValidation(RankedUserCreateValidation), rank=1)
            except InputValidationError as error:
                return error.graphql_type()
            return (await StrawchemyAsyncRepository(RankedUserType, info).create(user_input)).graphql_type()

        @strawchemy.field(graphql_type=RankedUserType, arguments=data_argument(RankedUserCreateInput))
        async def create_ranked_user(self, info: strawberry.Info, data: RankedUserCreateInput) -> RankedUserType:
            return (await StrawchemyAsyncRepository(RankedUserType, info).create(Input(data, rank=1))).graphql_type()

    return Operations(query=Query, mutation=Mutation)


@pytest.fixture
def schema(dialect: SupportedDialect) -> SchemaTypes:
    return SchemaTypes.build(dialect, _schema)


@pytest.fixture
def seed_insert_statements() -> list[Insert]:
    return [insert(Color).values(_COLORS)]


@pytest.mark.parametrize(
    ("query_name", "query"),
    [
        pytest.param(
            "createColor",
            """
            mutation {
                createColor(data: {  name: "new color" }) {
                    name
                }
            }
            """,
            id="createColor",
        ),
        pytest.param(
            "createValidatedColor",
            """
            mutation {
                createValidatedColor(data: {  name: "new color" }) {
                    ... on ColorType {
                        name
                    }
                }
            }
            """,
            id="createValidatedColor",
        ),
        pytest.param(
            "createColorManualValidation",
            """
            mutation {
                createColorManualValidation(data: {  name: "new color" }) {
                    ... on ColorType {
                        name
                    }
                }
            }
            """,
            id="createValidatedColor-manual",
        ),
        pytest.param(
            "createValidatedColor",
            """
            mutation {
                createValidatedColor(data: {  name: "new color" }) {
                    ... on ColorType {
                        name
                    }
                    ... on ValidationErrorType {
                        id
                        errors {
                            id
                            loc
                            message
                            type
                        }
                    }
                }
            }
            """,
            id="createValidatedColorAllFragments",
        ),
        pytest.param(
            "createColorManualValidation",
            """
            mutation {
                createColorManualValidation(data: {  name: "new color" }) {
                    ... on ColorType {
                        name
                    }
                    ... on ValidationErrorType {
                        id
                        errors {
                            id
                            loc
                            message
                            type
                        }
                    }
                }
            }
            """,
            id="createValidatedColorAllFragments-manual",
        ),
    ],
)
@pytest.mark.snapshot
async def test_create(
    query_name: str,
    query: str,
    any_async_query: AnyQueryExecutor,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:
    result = await maybe_async(any_async_query(query))
    assert not result.errors
    assert result.data
    assert result.data[query_name] == {"name": "new color"}

    insert_tracker, select_tracker = query_tracker.filter("insert"), query_tracker.filter("select")
    assert insert_tracker.query_count == 1
    assert select_tracker.query_count == 1
    assert insert_tracker[0].statement_formatted == sql_snapshot
    assert select_tracker[0].statement_formatted == sql_snapshot


async def test_create_validated_with_nested_relations_create(any_async_query: AnyQueryExecutor) -> None:
    query = """
            mutation {
                createValidatedColor(data: {
                    name: "white",
                    fruits: {
                        create: [
                            {
                                name: "Grape",
                                sweetness: 1,
                                waterPercent: 0.8,
                                product: { create: { name: "wine" } }
                            },
                            {
                                name: "Lychee",
                                sweetness: 1,
                                waterPercent: 0.7,
                                farms: { create: [ { name: "Bio farm" } ] }
                            },
                        ]
                    }
                }) {
                    ... on ColorType {
                        name
                        fruits {
                            name
                            product {
                                name
                            }
                            farms {
                                name
                            }
                        }
                    }
                }
            }
            """
    result = await maybe_async(any_async_query(query))
    assert not result.errors
    assert result.data
    assert result.data["createValidatedColor"]["name"] == "white"
    expected_fruits = [
        {"name": "Lychee", "product": None, "farms": [{"name": "Bio farm"}]},
        {"name": "Grape", "product": {"name": "wine"}, "farms": []},
    ]
    for fruit in expected_fruits:
        assert fruit in result.data["createValidatedColor"]["fruits"]


async def test_create_validated_with_nested_upsert(any_async_query: AnyQueryExecutor) -> None:
    query = """
            mutation {
                createValidatedColor(data: {
                    name: "white",
                    fruits: {
                        upsert: {
                            create: [
                                {
                                    name: "Plum",
                                    sweetness: 7,
                                    waterPercent: 0.87,
                                    product: { create: { name: "jam" } }
                                }
                            ]
                            conflictFields: name
                        }
                    }
                }) {
                    ... on ColorType {
                        name
                        fruits {
                            name
                            product {
                                name
                            }
                        }
                    }
                }
            }
            """
    result = await maybe_async(any_async_query(query))
    assert not result.errors
    assert result.data
    assert result.data["createValidatedColor"] == {
        "name": "white",
        "fruits": [{"name": "Plum", "product": {"name": "jam"}}],
    }


@pytest.mark.parametrize(
    ("query", "query_name"),
    [
        pytest.param(
            """
                mutation {{
                    updateColor(
                        data: {{
                            id: {color_id},
                            name: "updated color"
                        }}
                    ) {{
                        id
                        name
                    }}
                }}
                """,
            "updateColor",
            id="no-validation",
        ),
        pytest.param(
            """
                mutation {{
                    updateValidatedColor(
                        data: {{
                            id: {color_id},
                            name: "updated color"
                        }}
                    ) {{
                        ... on ColorType {{
                            id
                            name
                        }}
                        ... on ValidationErrorType {{
                            errorId: id
                            errors {{
                                id
                                loc
                                message
                                type
                            }}
                        }}
                    }}
                }}
                """,
            "updateValidatedColor",
            id="validation-fragment",
        ),
        pytest.param(
            """
                mutation {{
                    updateValidatedColor(
                        data: {{
                            id: {color_id},
                            name: "updated color"
                        }}
                    ) {{
                        ... on ColorType {{
                            id
                            name
                        }}
                    }}
                }}
                """,
            "updateValidatedColor",
            id="validation-no-fragment",
        ),
    ],
)
@pytest.mark.snapshot
async def test_update(
    query_name: str,
    query: str,
    any_async_query: AnyQueryExecutor,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:
    """Tests a simple update mutation."""
    result = await maybe_async(
        any_async_query(query.format(color_id=to_graphql_representation(_COLORS[0]["id"], "input")))
    )
    assert not result.errors
    assert result.data
    assert result.data[query_name] == {
        "id": to_graphql_representation(_COLORS[0]["id"], "output"),
        "name": "updated color",
    }

    query_tracker.assert_statements(1, "update", sql_snapshot)  # Update color name
    query_tracker.assert_statements(1, "select", sql_snapshot)  # Fetch id + name


@pytest.mark.parametrize(
    ("query_name", "query"),
    [
        pytest.param(
            "createValidatedRankedUser",
            """
        mutation {
            createValidatedRankedUser(data: {  name: "batman" }) {
                ... on RankedUserType {
                    name
                    rank
                }
                ... on ValidationErrorType {
                    id
                    errors {
                        id
                        loc
                        message
                        type
                    }
                }
            }
        }
        """,
            id="validation",
        ),
        pytest.param(
            "createRankedUser",
            """
        mutation {
            createRankedUser(data: {  name: "batman" }) {
                name
                rank
            }
        }
        """,
            id="validation",
        ),
    ],
)
async def test_read_only_column_override(query_name: str, query: str, any_async_query: AnyQueryExecutor) -> None:
    result = await maybe_async(any_async_query(query))
    assert not result.errors
    assert result.data
    assert result.data[query_name] == {"name": "batman", "rank": 1}
