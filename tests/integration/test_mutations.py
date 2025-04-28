from __future__ import annotations

from typing import cast

import pytest
from strawchemy import (
    Input,
    InputValidationError,
    StrawchemyAsyncRepository,
    StrawchemySyncRepository,
    ValidationErrorType,
)

import strawberry
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session
from syrupy.assertion import SnapshotAssertion
from tests.integration.models import Color, Fruit
from tests.integration.utils import to_graphql_representation
from tests.typing import AnyQueryExecutor
from tests.utils import maybe_async

from .fixtures import QueryTracker
from .types import (
    ColorCreateInput,
    ColorCreateValidation,
    ColorFilter,
    ColorPartial,
    ColorPkUpdateValidation,
    ColorType,
    ColorUpdateInput,
    FruitCreateInput,
    FruitType,
    FruitUpdateInput,
    RankedUserCreateInput,
    RankedUserCreateValidation,
    RankedUserType,
    UserCreate,
    UserFilter,
    UserType,
    UserUpdateInput,
    strawchemy,
)
from .typing import RawRecordData

pytestmark = [pytest.mark.integration]


@strawberry.type
class AsyncMutation:
    create_color: ColorType = strawchemy.create(ColorCreateInput, repository_type=StrawchemyAsyncRepository)
    create_validated_color: ColorType | ValidationErrorType = strawchemy.create(
        ColorCreateInput, validation=ColorCreateValidation, repository_type=StrawchemyAsyncRepository
    )
    create_colors: list[ColorType] = strawchemy.create(ColorCreateInput, repository_type=StrawchemyAsyncRepository)

    update_color: ColorType = strawchemy.update_by_ids(ColorUpdateInput, repository_type=StrawchemyAsyncRepository)
    update_validated_color: ColorType | ValidationErrorType = strawchemy.update_by_ids(
        ColorUpdateInput, validation=ColorPkUpdateValidation, repository_type=StrawchemyAsyncRepository
    )
    update_colors: list[ColorType] = strawchemy.update_by_ids(
        ColorUpdateInput, repository_type=StrawchemyAsyncRepository
    )
    update_colors_filter: list[ColorType] = strawchemy.update(
        ColorPartial, ColorFilter, repository_type=StrawchemyAsyncRepository
    )

    create_fruit: FruitType = strawchemy.create(FruitCreateInput, repository_type=StrawchemyAsyncRepository)
    create_fruits: list[FruitType] = strawchemy.create(FruitCreateInput, repository_type=StrawchemyAsyncRepository)

    update_fruit: FruitType = strawchemy.update_by_ids(FruitUpdateInput, repository_type=StrawchemyAsyncRepository)
    update_fruits: list[FruitType] = strawchemy.update_by_ids(
        FruitUpdateInput, repository_type=StrawchemyAsyncRepository
    )

    update_user: UserType = strawchemy.update_by_ids(UserUpdateInput, repository_type=StrawchemyAsyncRepository)

    create_user: UserType = strawchemy.create(UserCreate, repository_type=StrawchemyAsyncRepository)

    delete_users: list[UserType] = strawchemy.delete(repository_type=StrawchemyAsyncRepository)
    delete_users_filter: list[UserType] = strawchemy.delete(UserFilter, repository_type=StrawchemyAsyncRepository)

    @strawberry.field
    async def create_blue_color(self, info: strawberry.Info, data: ColorCreateInput) -> ColorType:
        return await StrawchemyAsyncRepository(ColorType, info).create(Input(data, name="Blue"))

    @strawberry.field
    async def create_apple_color(self, info: strawberry.Info, data: ColorCreateInput) -> ColorType:
        color_input = Input(data)
        color_input.instances[0].fruits.extend([Fruit(name="Apple"), Fruit(name="Strawberry")])
        return await StrawchemyAsyncRepository(ColorType, info).create(color_input)

    @strawberry.field
    async def create_color_for_existing_fruits(self, info: strawberry.Info, data: ColorCreateInput) -> ColorType:
        color_input = Input(data)
        session = cast(AsyncSession, info.context.session)
        apple, strawberry = Fruit(name="Apple"), Fruit(name="Strawberry")
        session.add_all([apple, strawberry])
        await session.commit()
        session.expire(strawberry)
        color_input.instances[0].fruits.extend([apple, strawberry])
        return await StrawchemyAsyncRepository(ColorType, info).create(color_input)

    @strawberry.field
    async def create_red_fruit(self, info: strawberry.Info, data: FruitCreateInput) -> FruitType:
        fruit_input = Input(data)
        fruit_input.instances[0].color = Color(name="Red")
        return await StrawchemyAsyncRepository(FruitType, info).create(fruit_input)

    @strawberry.field
    async def create_fruit_for_existing_color(self, info: strawberry.Info, data: FruitCreateInput) -> FruitType:
        fruit_input = Input(data)
        session = cast(AsyncSession, info.context.session)
        red = Color(name="Red")
        session.add(red)
        await session.commit()
        fruit_input.instances[0].color = red
        return await StrawchemyAsyncRepository(FruitType, info).create(fruit_input)

    @strawberry.field
    async def create_color_manual_validation(
        self, info: strawberry.Info, data: ColorCreateInput
    ) -> ColorType | ValidationErrorType:
        try:
            return await StrawchemyAsyncRepository(ColorType, info).create(
                Input(data, validation=ColorCreateValidation)
            )
        except InputValidationError as error:
            return ValidationErrorType.from_pydantic(error.pydantic_error)

    @strawberry.field
    async def create_validated_ranked_user(
        self, info: strawberry.Info, data: RankedUserCreateInput
    ) -> RankedUserType | ValidationErrorType:
        try:
            return await StrawchemyAsyncRepository(RankedUserType, info).create(
                Input(data, validation=RankedUserCreateValidation, rank=1)
            )
        except InputValidationError as error:
            return ValidationErrorType.from_pydantic(error.pydantic_error)

    @strawberry.field
    async def create_ranked_user(self, info: strawberry.Info, data: RankedUserCreateInput) -> RankedUserType:
        return await StrawchemyAsyncRepository(RankedUserType, info).create(Input(data, rank=1))


@strawberry.type
class SyncMutation:
    create_color: ColorType = strawchemy.create(ColorCreateInput, repository_type=StrawchemySyncRepository)
    create_validated_color: ColorType | ValidationErrorType = strawchemy.create(
        ColorCreateInput, validation=ColorCreateValidation, repository_type=StrawchemySyncRepository
    )
    create_colors: list[ColorType] = strawchemy.create(ColorCreateInput, repository_type=StrawchemySyncRepository)

    create_fruit: FruitType = strawchemy.create(FruitCreateInput, repository_type=StrawchemySyncRepository)
    update_color: ColorType = strawchemy.update_by_ids(ColorUpdateInput, repository_type=StrawchemySyncRepository)
    update_validated_color: ColorType | ValidationErrorType = strawchemy.update_by_ids(
        ColorUpdateInput, validation=ColorPkUpdateValidation, repository_type=StrawchemySyncRepository
    )
    update_colors: list[ColorType] = strawchemy.update_by_ids(
        ColorUpdateInput, repository_type=StrawchemySyncRepository
    )
    update_colors_filter: list[ColorType] = strawchemy.update(
        ColorPartial, ColorFilter, repository_type=StrawchemySyncRepository
    )

    create_fruits: list[FruitType] = strawchemy.create(FruitCreateInput, repository_type=StrawchemySyncRepository)

    create_user: UserType = strawchemy.create(UserCreate, repository_type=StrawchemySyncRepository)

    update_fruit: FruitType = strawchemy.update_by_ids(FruitUpdateInput, repository_type=StrawchemySyncRepository)
    update_fruits: list[FruitType] = strawchemy.update_by_ids(
        FruitUpdateInput, repository_type=StrawchemySyncRepository
    )

    update_user: UserType = strawchemy.update_by_ids(UserUpdateInput, repository_type=StrawchemySyncRepository)
    delete_users: list[UserType] = strawchemy.delete(repository_type=StrawchemySyncRepository)
    delete_users_filter: list[UserType] = strawchemy.delete(UserFilter, repository_type=StrawchemySyncRepository)

    @strawberry.field
    def create_blue_color(self, info: strawberry.Info, data: ColorCreateInput) -> ColorType:
        return StrawchemySyncRepository(ColorType, info).create(Input(data, name="Blue"))

    @strawberry.field
    def create_apple_color(self, info: strawberry.Info, data: ColorCreateInput) -> ColorType:
        color_input = Input(data)
        color_input.instances[0].fruits.extend([Fruit(name="Apple"), Fruit(name="Strawberry")])
        return StrawchemySyncRepository(ColorType, info).create(color_input)

    @strawberry.field
    def create_color_for_existing_fruits(self, info: strawberry.Info, data: ColorCreateInput) -> ColorType:
        color_input = Input(data)
        session = cast(Session, info.context.session)
        apple, strawberry = Fruit(name="Apple"), Fruit(name="Strawberry")
        session.add_all([apple, strawberry])
        session.commit()
        session.expire(strawberry)
        color_input.instances[0].fruits.extend([apple, strawberry])
        return StrawchemySyncRepository(ColorType, info).create(color_input)

    @strawberry.field
    def create_red_fruit(self, info: strawberry.Info, data: FruitCreateInput) -> FruitType:
        fruit_input = Input(data)
        fruit_input.instances[0].color = Color(name="Red")
        return StrawchemySyncRepository(FruitType, info).create(fruit_input)

    @strawberry.field
    def create_fruit_for_existing_color(self, info: strawberry.Info, data: FruitCreateInput) -> FruitType:
        fruit_input = Input(data)
        session = cast(Session, info.context.session)
        red = Color(name="Red")
        session.add(red)
        session.commit()
        fruit_input.instances[0].color = red
        return StrawchemySyncRepository(FruitType, info).create(fruit_input)

    @strawberry.field
    def create_color_manual_validation(
        self, info: strawberry.Info, data: ColorCreateInput
    ) -> ColorType | ValidationErrorType:
        try:
            return StrawchemySyncRepository(ColorType, info).create(Input(data, validation=ColorCreateValidation))
        except InputValidationError as error:
            return ValidationErrorType.from_pydantic(error.pydantic_error)

    @strawberry.field
    def create_validated_ranked_user(
        self, info: strawberry.Info, data: RankedUserCreateInput
    ) -> RankedUserType | ValidationErrorType:
        try:
            return StrawchemySyncRepository(RankedUserType, info).create(
                Input(data, validation=RankedUserCreateValidation, rank=1)
            )
        except InputValidationError as error:
            return ValidationErrorType.from_pydantic(error.pydantic_error)

    @strawberry.field
    def create_ranked_user(self, info: strawberry.Info, data: RankedUserCreateInput) -> RankedUserType:
        return StrawchemySyncRepository(RankedUserType, info).create(Input(data, rank=1))


@pytest.fixture
def sync_mutation() -> type[SyncMutation]:
    return SyncMutation


@pytest.fixture
def async_mutation() -> type[AsyncMutation]:
    return AsyncMutation


# Create tests


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
    any_query: AnyQueryExecutor,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:
    result = await maybe_async(any_query(query))
    assert not result.errors
    assert result.data
    assert result.data[query_name] == {"name": "new color"}

    insert_tracker, select_tracker = query_tracker.filter("insert"), query_tracker.filter("select")
    assert insert_tracker.query_count == 1
    assert select_tracker.query_count == 1
    assert insert_tracker[0].statement_formatted == sql_snapshot
    assert select_tracker[0].statement_formatted == sql_snapshot


@pytest.mark.snapshot
async def test_create_with_to_one_set(
    raw_colors: RawRecordData, any_query: AnyQueryExecutor, query_tracker: QueryTracker, sql_snapshot: SnapshotAssertion
) -> None:
    query = """
        mutation {{
            createFruit(data: {{
                name: "new fruit",
                adjectives: ["foo", "bar"],
                color: {{
                    set: {{ id: {color_id} }}
                }}
            }}) {{
                name
                color {{
                    id
                }}
            }}
        }}
    """
    result = await maybe_async(
        any_query(query.format(color_id=to_graphql_representation(raw_colors[0]["id"], "input")))
    )
    assert not result.errors
    assert result.data
    assert result.data["createFruit"] == {
        "name": "new fruit",
        "color": {"id": to_graphql_representation(raw_colors[0]["id"], "output")},
    }

    query_tracker.assert_statements(1, "select", sql_snapshot)
    query_tracker.assert_statements(1, "insert", sql_snapshot)


@pytest.mark.snapshot
async def test_create_with_to_one_set_null(
    raw_colors: RawRecordData, any_query: AnyQueryExecutor, query_tracker: QueryTracker, sql_snapshot: SnapshotAssertion
) -> None:
    query = """
        mutation {{
            createFruit(data: {{
                name: "new fruit",
                adjectives: ["foo", "bar"],
                color: {{ set: null }}
            }}) {{
                name
                color {{
                    id
                }}
            }}
        }}
    """
    result = await maybe_async(
        any_query(query.format(color_id=to_graphql_representation(raw_colors[0]["id"], "input")))
    )
    assert not result.errors
    assert result.data
    assert result.data["createFruit"] == {"name": "new fruit", "color": None}

    query_tracker.assert_statements(1, "select", sql_snapshot)
    query_tracker.assert_statements(1, "insert", sql_snapshot)


@pytest.mark.snapshot
async def test_create_with_to_one_create(
    any_query: AnyQueryExecutor, query_tracker: QueryTracker, sql_snapshot: SnapshotAssertion
) -> None:
    query = """
            mutation {
                createFruit(data: {
                    name: "new color",
                    adjectives: ["foo", "bar"],
                    color: {
                        create: { name: "new sub color" }
                    }
                }) {
                    name
                    color {
                        name
                    }
                }
            }
            """
    result = await maybe_async(any_query(query))
    assert not result.errors
    assert result.data
    assert result.data["createFruit"] == {"name": "new color", "color": {"name": "new sub color"}}

    query_tracker.assert_statements(1, "select", sql_snapshot)
    query_tracker.assert_statements(2, "insert", sql_snapshot)


@pytest.mark.snapshot
async def test_create_with_to_one_create_and_nested_set(
    raw_topics: RawRecordData, any_query: AnyQueryExecutor, query_tracker: QueryTracker, sql_snapshot: SnapshotAssertion
) -> None:
    query = """
            mutation {{
                createUser(data: {{
                    name: "Bob",
                    group: {{
                        create: {{
                            name: "new group",
                            topics: {{ set: [ {{ id: {topic_id} }} ] }}
                        }}
                    }}
                }}) {{
                    name
                    group {{
                        name
                        topics {{
                            id
                        }}
                    }}
                }}
            }}
            """
    result = await maybe_async(
        any_query(query.format(topic_id=to_graphql_representation(raw_topics[0]["id"], "input")))
    )
    assert not result.errors
    assert result.data
    assert result.data["createUser"] == {
        "name": "Bob",
        "group": {"name": "new group", "topics": [{"id": to_graphql_representation(raw_topics[0]["id"], "output")}]},
    }

    query_tracker.assert_statements(1, "select", sql_snapshot)
    query_tracker.assert_statements(2, "insert", sql_snapshot)


@pytest.mark.parametrize(
    "query",
    [
        pytest.param(
            """
        mutation {{
            createColor(data: {{
                name: "new color",
                fruits: {{
                    set: [{{ id: {fruit_id} }}]
                }}
            }}) {{
                name
                fruits {{
                    id
                }}
            }}
        }}
        """,
            id="set",
        ),
        pytest.param(
            """
        mutation {{
            createColor(data: {{
                name: "new color",
                fruits: {{
                    add: [{{ id: {fruit_id} }}]
                }}
            }}) {{
                name
                fruits {{
                    id
                }}
            }}
        }}
        """,
            id="add",
        ),
    ],
)
@pytest.mark.snapshot
async def test_create_with_existing_to_many(
    query: str,
    raw_fruits: RawRecordData,
    any_query: AnyQueryExecutor,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:
    result = await maybe_async(
        any_query(query.format(fruit_id=to_graphql_representation(raw_fruits[0]["id"], "input")))
    )
    assert not result.errors
    assert result.data
    assert result.data["createColor"] == {
        "name": "new color",
        "fruits": [{"id": to_graphql_representation(raw_fruits[0]["id"], "output")}],
    }

    query_tracker.assert_statements(1, "select", sql_snapshot)
    query_tracker.assert_statements(1, "insert", sql_snapshot)
    query_tracker.assert_statements(1, "update", sql_snapshot)


@pytest.mark.snapshot
async def test_create_with_to_many_create(
    any_query: AnyQueryExecutor, query_tracker: QueryTracker, sql_snapshot: SnapshotAssertion
) -> None:
    query = """
            mutation {
                createColor(data: {
                    name: "new color",
                    fruits: {
                        create: [
                            { name: "new fruit 1", adjectives: ["foo"] },
                            { name: "new fruit 2", adjectives: ["bar"] }
                        ]
                    }
                }) {
                    name
                    fruits {
                        name
                    }
                }
            }
            """
    result = await maybe_async(any_query(query))
    assert not result.errors
    assert result.data
    assert result.data["createColor"] == {
        "name": "new color",
        "fruits": [{"name": "new fruit 1"}, {"name": "new fruit 2"}],
    }

    query_tracker.assert_statements(2, "insert", sql_snapshot)
    query_tracker.assert_statements(1, "select", sql_snapshot)


@pytest.mark.parametrize(
    "query",
    [
        pytest.param(
            """
            mutation {{
                createColor(data: {{
                    name: "new color",
                    fruits: {{
                        set: [ {{ id: {fruit_id} }} ],
                        add: [ {{ id: {fruit_id} }} ]
                    }}
                }}) {{
                    name
                    fruits {{
                        name
                    }}
                }}
            }}
        """,
            id="add",
        ),
        pytest.param(
            """
            mutation {{
                createColor(data: {{
                    name: "new color",
                    fruits: {{
                        set: [ {{ id: {fruit_id} }} ],
                        create: [ {{ name: "new fruit 1", adjectives: ["foo"] }} ]
                    }}
                }}) {{
                    name
                    fruits {{
                        name
                    }}
                }}
            }}
        """,
            id="create",
        ),
    ],
)
async def test_create_with_to_many_set_exclusive_with_add_and_create(
    query: str, raw_fruits: RawRecordData, any_query: AnyQueryExecutor
) -> None:
    result = await maybe_async(
        any_query(query.format(fruit_id=to_graphql_representation(raw_fruits[0]["id"], "input")))
    )
    assert not result.data
    assert result.errors
    assert len(result.errors) == 1
    assert result.errors[0].args[0] == "You cannot use `set` with `create` or `add` in -to-many relation input"


@pytest.mark.snapshot
async def test_create_with_to_many_create_and_nested_set(
    raw_farms: RawRecordData, any_query: AnyQueryExecutor, query_tracker: QueryTracker, sql_snapshot: SnapshotAssertion
) -> None:
    query = """
            mutation {{
                createColor(data: {{
                    name: "White",
                    fruits: {{
                        create: [
                            {{
                                name: "Grape",
                                adjectives: ["tangy", "juicy"],
                                farms: {{ set: [ {{ id: {farm_id} }} ] }}
                            }},
                        ]
                    }}
                }}) {{
                    name
                    fruits {{
                        name
                        farms {{
                            id
                        }}
                    }}
                }}
            }}
            """
    result = await maybe_async(any_query(query.format(farm_id=to_graphql_representation(raw_farms[0]["id"], "input"))))
    assert not result.errors
    assert result.data
    assert result.data["createColor"] == {
        "name": "White",
        "fruits": [{"name": "Grape", "farms": [{"id": to_graphql_representation(raw_farms[0]["id"], "output")}]}],
    }

    query_tracker.assert_statements(1, "select", sql_snapshot)
    query_tracker.assert_statements(2, "insert", sql_snapshot)


@pytest.mark.snapshot
async def test_create_with_nested_mixed_relations_create(
    any_query: AnyQueryExecutor, query_tracker: QueryTracker, sql_snapshot: SnapshotAssertion
) -> None:
    query = """
            mutation {
                createColor(data: {
                    name: "White",
                    fruits: {
                        create: [
                            {
                                name: "Grape",
                                product: { create: { name: "wine" } },
                                adjectives: ["tangy", "juicy"]
                            },
                            {
                                name: "Lychee",
                                farms: { create: [ { name: "Bio farm" } ] },
                                adjectives: ["sweet", "floral"]
                            },
                        ]
                    }
                }) {
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
            """
    result = await maybe_async(any_query(query))
    assert not result.errors
    assert result.data
    assert result.data["createColor"] == {
        "name": "White",
        "fruits": [
            {"name": "Lychee", "product": None, "farms": [{"name": "Bio farm"}]},
            {"name": "Grape", "product": {"name": "wine"}, "farms": []},
        ],
    }

    # Heterogeneous params means inserts cannot be batched
    query_tracker.assert_statements(5, "insert", sql_snapshot)
    query_tracker.assert_statements(1, "select", sql_snapshot)


@pytest.mark.snapshot
async def test_create_many(
    any_query: AnyQueryExecutor, query_tracker: QueryTracker, sql_snapshot: SnapshotAssertion
) -> None:
    result = await maybe_async(
        any_query(
            """
                mutation {
                    createColors(
                        data: [
                            { name: "new color 1" }
                            { name: "new color 2" }
                        ]
                    ) {
                        name
                    }
                }
            """
        )
    )
    assert not result.errors
    assert result.data
    assert result.data["createColors"] == [{"name": "new color 1"}, {"name": "new color 2"}]

    query_tracker.assert_statements(1, "insert", sql_snapshot)
    query_tracker.assert_statements(1, "select", sql_snapshot)


# Update tests


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
    raw_colors: RawRecordData,
    any_query: AnyQueryExecutor,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:
    """Tests a simple update mutation."""
    result = await maybe_async(
        any_query(query.format(color_id=to_graphql_representation(raw_colors[0]["id"], "input")))
    )
    assert not result.errors
    assert result.data
    assert result.data[query_name] == {
        "id": to_graphql_representation(raw_colors[0]["id"], "output"),
        "name": "updated color",
    }

    query_tracker.assert_statements(1, "update", sql_snapshot)  # Update color name
    query_tracker.assert_statements(1, "select", sql_snapshot)  # Fetch id + name


@pytest.mark.snapshot
async def test_update_by_filter(
    raw_colors: RawRecordData, any_query: AnyQueryExecutor, query_tracker: QueryTracker, sql_snapshot: SnapshotAssertion
) -> None:
    """Tests a simple update mutation."""
    query = """
        mutation {
            updateColorsFilter(
                data: {
                    name: "updated color"
                },
                filter: {
                    name: { eq: "Red" }
                }
            ) {
                id
                name
            }
        }
    """
    result = await maybe_async(any_query(query))
    assert not result.errors
    assert result.data
    assert result.data["updateColorsFilter"] == [
        {
            "id": to_graphql_representation(raw_colors[0]["id"], "output"),
            "name": "updated color",
        }
    ]

    query_tracker.assert_statements(1, "update", sql_snapshot)  # Update color name
    query_tracker.assert_statements(1, "select", sql_snapshot)  # Fetch id + name


@pytest.mark.snapshot
async def test_update_by_filter_only_return_affected_objects(
    any_query: AnyQueryExecutor, query_tracker: QueryTracker, sql_snapshot: SnapshotAssertion
) -> None:
    """Tests a simple update mutation."""
    query = """
        mutation {
            updateColorsFilter(
                data: {
                    name: "updated color"
                },
                filter: {
                    name: { eq: "unknown" }
                }
            ) {
                id
                name
            }
        }
    """
    result = await maybe_async(any_query(query))
    assert not result.errors
    assert result.data
    assert result.data["updateColorsFilter"] == []

    query_tracker.assert_statements(1, "update", sql_snapshot)  # Update color name
    query_tracker.assert_statements(1, "select", sql_snapshot)  # Fetch id + name


@pytest.mark.snapshot
async def test_update_with_to_one_set(
    raw_fruits: RawRecordData,
    raw_colors: RawRecordData,
    any_query: AnyQueryExecutor,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:
    """Tests updating a record and setting a to-one relationship."""
    fruit_id_gql = to_graphql_representation(raw_fruits[0]["id"], "input")
    # Use a different color to test the update
    color_id_gql = to_graphql_representation(raw_colors[1]["id"], "input")
    query = f"""
        mutation {{
            updateFruit(
                data: {{
                    id: {fruit_id_gql},
                    name: "updated fruit name",
                    color: {{ set: {{ id: {color_id_gql} }} }}
                }}
            ) {{
                id
                name
                color {{
                    id
                }}
            }}
        }}
    """
    result = await maybe_async(any_query(query))
    assert not result.errors
    assert result.data
    assert result.data["updateFruit"] == {
        "id": to_graphql_representation(raw_fruits[0]["id"], "output"),
        "name": "updated fruit name",
        "color": {"id": to_graphql_representation(raw_colors[1]["id"], "output")},
    }

    query_tracker.assert_statements(1, "update", sql_snapshot)  # Update fruit's color_id
    query_tracker.assert_statements(1, "select", sql_snapshot)  # Fetch updated fruit + color


@pytest.mark.snapshot
async def test_update_with_to_one_set_null(
    raw_fruits: RawRecordData, any_query: AnyQueryExecutor, query_tracker: QueryTracker, sql_snapshot: SnapshotAssertion
) -> None:
    """Tests updating a record and setting a to-one relationship."""
    fruit_id_gql = to_graphql_representation(raw_fruits[0]["id"], "input")
    query = f"""
        mutation {{
            updateFruit(
                data: {{
                    id: {fruit_id_gql},
                    name: "updated fruit name",
                    color: {{ set: null }}
                }}
            ) {{
                id
                name
                color {{
                    id
                }}
            }}
        }}
    """
    result = await maybe_async(any_query(query))
    assert not result.errors
    assert result.data
    assert result.data["updateFruit"] == {
        "id": to_graphql_representation(raw_fruits[0]["id"], "output"),
        "name": "updated fruit name",
        "color": None,
    }

    query_tracker.assert_statements(1, "update", sql_snapshot)  # Update fruit's color_id
    query_tracker.assert_statements(1, "select", sql_snapshot)  # Fetch updated fruit + color


@pytest.mark.snapshot
async def test_update_with_to_one_create(
    raw_fruits: RawRecordData, any_query: AnyQueryExecutor, query_tracker: QueryTracker, sql_snapshot: SnapshotAssertion
) -> None:
    """Tests updating a record and creating a new related record for a to-one relationship."""
    fruit_id_gql = to_graphql_representation(raw_fruits[0]["id"], "input")
    query = f"""
        mutation {{
            updateFruit(
                data: {{
                    id: {fruit_id_gql},
                    name: "updated fruit name 2",
                    color: {{ create: {{ name: "newly created color during update" }} }}
                }}
            ) {{
                id
                name
                color {{
                    name
                }}
            }}
        }}
    """
    result = await maybe_async(any_query(query))
    assert not result.errors
    assert result.data
    assert result.data["updateFruit"] == {
        "id": to_graphql_representation(raw_fruits[0]["id"], "output"),
        "name": "updated fruit name 2",
        "color": {"name": "newly created color during update"},
    }

    query_tracker.assert_statements(1, "insert", sql_snapshot)  # Insert new color
    query_tracker.assert_statements(1, "update", sql_snapshot)  # Update fruit's color_id
    query_tracker.assert_statements(1, "select", sql_snapshot)  # Fetch updated fruit + new color


async def test_update_with_to_one_set_and_create_fail(
    raw_fruits: RawRecordData, raw_colors: RawRecordData, any_query: AnyQueryExecutor
) -> None:
    """Tests updating a record and setting a to-one relationship."""
    fruit_id_gql = to_graphql_representation(raw_fruits[0]["id"], "input")
    # Use a different color to test the update
    color_id_gql = to_graphql_representation(raw_colors[1]["id"], "input")
    query = f"""
        mutation {{
            updateFruit(
                data: {{
                    id: {fruit_id_gql},
                    name: "updated fruit name",
                    color: {{
                        set: {{ id: {color_id_gql} }},
                        create: {{ name: "newly created color during update" }}
                    }}
                }}
            ) {{
                id
                name
                color {{
                    id
                }}
            }}
        }}
    """
    result = await maybe_async(any_query(query))
    assert not result.data
    assert result.errors
    assert len(result.errors) == 1
    assert result.errors[0].args[0] == "You cannot use both `set` and `create` in a -to-one relation input"


@pytest.mark.snapshot
async def test_update_with_to_one_create_and_nested_set(
    raw_users: RawRecordData,
    raw_topics: RawRecordData,
    any_query: AnyQueryExecutor,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:
    """Tests updating a record and creating a nested related record which itself sets a relationship."""
    user_id_gql = to_graphql_representation(raw_users[0]["id"], "input")
    # Use a different topic to test the update/create
    topic_id_gql = to_graphql_representation(raw_topics[1]["id"], "input")
    query = f"""
        mutation {{
            updateUser(
                data: {{
                    id: {user_id_gql},
                    name: "Updated Bob",
                    group: {{
                        create: {{
                            name: "new group during update",
                            topics: {{ set: [ {{ id: {topic_id_gql} }} ] }}
                        }}
                    }}
                }}
            ) {{
                id
                name
                group {{
                    name
                    topics {{
                        id
                    }}
                }}
            }}
        }}
    """
    result = await maybe_async(any_query(query))
    assert not result.errors
    assert result.data
    assert result.data["updateUser"] == {
        "id": to_graphql_representation(raw_users[0]["id"], "output"),
        "name": "Updated Bob",
        "group": {
            "name": "new group during update",
            "topics": [{"id": to_graphql_representation(raw_topics[1]["id"], "output")}],
        },
    }

    query_tracker.assert_statements(1, "insert", sql_snapshot)  # Insert new group
    query_tracker.assert_statements(2, "update", sql_snapshot)  # Update user's group_id and topic's group id
    query_tracker.assert_statements(1, "select", sql_snapshot)  # Fetch updated user + new group + topic


@pytest.mark.snapshot
async def test_update_with_to_many_set(
    raw_colors: RawRecordData,
    raw_fruits: RawRecordData,
    any_query: AnyQueryExecutor,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:
    """Tests updating a record and setting (replacing) a to-many relationship."""
    color_id_gql = to_graphql_representation(raw_colors[0]["id"], "input")
    # Use a different fruit to test the update
    fruit_id_gql = to_graphql_representation(raw_fruits[1]["id"], "input")
    query = f"""
        mutation {{
            updateColor(
                data: {{
                    id: {color_id_gql},
                    name: "updated color name",
                    fruits: {{ set: [{{ id: {fruit_id_gql} }}] }}
                }}
            ) {{
                id
                name
                fruits {{
                    id
                }}
            }}
        }}
    """
    result = await maybe_async(any_query(query))
    assert not result.errors
    assert result.data
    assert result.data["updateColor"] == {
        "id": to_graphql_representation(raw_colors[0]["id"], "output"),
        "name": "updated color name",
        "fruits": [{"id": to_graphql_representation(raw_fruits[1]["id"], "output")}],
    }

    # 1. Disconnect previous fruit
    # 2. Update specified fruit's color_id
    # 3. Update color's name
    query_tracker.assert_statements(3, "update", sql_snapshot)
    # Fetch updated color + fruit
    query_tracker.assert_statements(1, "select", sql_snapshot)


@pytest.mark.snapshot
async def test_update_with_to_many_remove(
    raw_colors: RawRecordData,
    raw_fruits: RawRecordData,
    any_query: AnyQueryExecutor,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:
    """Tests updating a record and setting (replacing) a to-many relationship."""
    color_id_gql = to_graphql_representation(raw_colors[0]["id"], "input")
    # Remove the existing fruit
    fruit_id_gql = to_graphql_representation(raw_fruits[0]["id"], "input")
    query = f"""
        mutation {{
            updateColor(
                data: {{
                    id: {color_id_gql},
                    name: "updated color name",
                    fruits: {{ remove: [{{ id: {fruit_id_gql} }}] }}
                }}
            ) {{
                id
                name
                fruits {{
                    id
                }}
            }}
        }}
    """
    result = await maybe_async(any_query(query))
    assert not result.errors
    assert result.data
    assert result.data["updateColor"] == {
        "id": to_graphql_representation(raw_colors[0]["id"], "output"),
        "name": "updated color name",
        "fruits": [],
    }

    # 1. Update specified fruit's color_id
    # 2. Update color's name
    query_tracker.assert_statements(2, "update", sql_snapshot)
    # Fetch updated color + fruit
    query_tracker.assert_statements(1, "select", sql_snapshot)


@pytest.mark.snapshot
async def test_update_with_to_many_create(
    raw_fruits: RawRecordData,
    raw_colors: RawRecordData,
    any_query: AnyQueryExecutor,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:
    """Tests updating a record and creating new related records for a to-many relationship."""
    color_id_gql = to_graphql_representation(raw_colors[0]["id"], "input")
    query = f"""
        mutation {{
            updateColor(
                data: {{
                    id: {color_id_gql},
                    name: "updated color name 2",
                    fruits: {{
                        create: [
                            {{ name: "new fruit 3 during update", adjectives: ["baz"] }},
                            {{ name: "new fruit 4 during update", adjectives: ["qux"] }}
                        ]
                    }}
                }}
            ) {{
                id
                name
                fruits {{
                    name # Check names of newly created fruits
                }}
            }}
        }}
    """
    result = await maybe_async(any_query(query))
    assert not result.errors
    assert result.data
    # The order might vary, sort for assertion stability
    fruits_data = sorted(result.data["updateColor"]["fruits"], key=lambda x: x["name"])
    assert result.data["updateColor"]["id"] == to_graphql_representation(raw_colors[0]["id"], "output")
    assert result.data["updateColor"]["name"] == "updated color name 2"
    assert fruits_data == [
        {"name": raw_fruits[0]["name"]},
        {"name": "new fruit 3 during update"},
        {"name": "new fruit 4 during update"},
    ]

    query_tracker.assert_statements(1, "insert", sql_snapshot)  # Insert 2 new fruits, in a single batched query
    query_tracker.assert_statements(1, "update", sql_snapshot)  # Update color name
    query_tracker.assert_statements(1, "select", sql_snapshot)  # Fetch updated color + new fruits


@pytest.mark.snapshot
async def test_update_with_to_many_create_and_nested_set(
    raw_colors: RawRecordData,
    raw_farms: RawRecordData,
    raw_fruits: RawRecordData,
    any_query: AnyQueryExecutor,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:
    """Tests updating a record and creating a nested related record which itself sets a to-many relationship."""
    color_id_gql = to_graphql_representation(raw_colors[0]["id"], "input")
    # Use a different farm
    farm_id_gql = to_graphql_representation(raw_farms[1]["id"], "input")
    query = f"""
        mutation {{
            updateColor(
                data: {{
                    id: {color_id_gql},
                    name: "Updated White",
                    fruits: {{
                        create: [
                            {{
                                name: "New Grape during update",
                                adjectives: ["sour", "small"],
                                farms: {{ set: [ {{ id: {farm_id_gql} }} ] }}
                            }}
                        ]
                    }}
                }}
            ) {{
                id
                name
                fruits {{
                    name
                    farms {{
                        id
                    }}
                }}
            }}
        }}
    """
    result = await maybe_async(any_query(query))
    assert not result.errors
    assert result.data
    assert result.data["updateColor"] == {
        "id": to_graphql_representation(raw_colors[0]["id"], "output"),
        "name": "Updated White",
        "fruits": [
            # Existing fruit
            {
                "name": raw_fruits[0]["name"],
                "farms": [
                    {
                        "id": to_graphql_representation(farm["id"], "output")  # noqa: B035
                        for farm in raw_farms
                        if farm["fruit_id"] == raw_fruits[0]["id"]
                    }
                ],
            },
            # New one
            {
                "name": "New Grape during update",
                "farms": [{"id": to_graphql_representation(raw_farms[1]["id"], "output")}],
            },
        ],
    }

    query_tracker.assert_statements(1, "insert", sql_snapshot)  # Insert new fruit
    query_tracker.assert_statements(2, "update", sql_snapshot)  # Update color name + fruit's farm_id
    query_tracker.assert_statements(1, "select", sql_snapshot)  # Fetch updated color + new fruit + farm


@pytest.mark.snapshot
async def test_update_with_to_many_add(
    raw_colors: RawRecordData,
    raw_fruits: RawRecordData,
    any_query: AnyQueryExecutor,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:
    """Tests updating a record and setting (replacing) a to-many relationship."""
    color_id_gql = to_graphql_representation(raw_colors[0]["id"], "input")
    # Use a different fruit to test the update
    fruit_id_gql = to_graphql_representation(raw_fruits[1]["id"], "input")
    query = f"""
        mutation {{
            updateColor(
                data: {{
                    id: {color_id_gql},
                    name: "updated color name",
                    fruits: {{ add: [{{ id: {fruit_id_gql} }}] }}
                }}
            ) {{
                id
                name
                fruits {{
                    id
                }}
            }}
        }}
    """
    result = await maybe_async(any_query(query))
    assert not result.errors
    assert result.data
    assert result.data["updateColor"] == {
        "id": to_graphql_representation(raw_colors[0]["id"], "output"),
        "name": "updated color name",
        "fruits": [
            {"id": to_graphql_representation(raw_fruits[0]["id"], "output")},
            {"id": to_graphql_representation(raw_fruits[1]["id"], "output")},
        ],
    }

    # 1. Update specified fruit's color_id
    # 2. Update color's name
    query_tracker.assert_statements(2, "update", sql_snapshot)
    # Fetch updated color + fruit
    query_tracker.assert_statements(1, "select", sql_snapshot)


@pytest.mark.snapshot
async def test_update_with_to_many_add_and_create(
    raw_colors: RawRecordData,
    raw_fruits: RawRecordData,
    any_query: AnyQueryExecutor,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:
    """Tests updating a record and setting (replacing) a to-many relationship."""
    color_id_gql = to_graphql_representation(raw_colors[0]["id"], "input")
    # Use a different fruit to test the update
    fruit_id_gql = to_graphql_representation(raw_fruits[1]["id"], "input")
    query = f"""
        mutation {{
            updateColor(
                data: {{
                    id: {color_id_gql},
                    name: "updated color name",
                    fruits: {{
                        add: [{{ id: {fruit_id_gql} }}],
                        create: [{{ name: "new fruit 3 during update", adjectives: ["baz"] }}]
                    }}
                }}
            ) {{
                id
                name
                fruits {{
                    name
                }}
            }}
        }}
    """
    result = await maybe_async(any_query(query))
    assert not result.errors
    assert result.data
    assert result.data["updateColor"] == {
        "id": to_graphql_representation(raw_colors[0]["id"], "output"),
        "name": "updated color name",
        "fruits": [
            {"name": to_graphql_representation(raw_fruits[0]["name"], "output")},
            {"name": "new fruit 3 during update"},
            {"name": to_graphql_representation(raw_fruits[1]["name"], "output")},
        ],
    }

    query_tracker.assert_statements(1, "insert", sql_snapshot)
    # 1. Update specified fruit's color_id
    # 2. Update color's name
    query_tracker.assert_statements(2, "update", sql_snapshot)
    # Fetch updated color + fruit
    query_tracker.assert_statements(1, "select", sql_snapshot)


@pytest.mark.parametrize(
    "query",
    [
        pytest.param(
            """
        mutation {{
            updateColor(
                data: {{
                    id: {color_id_gql},
                    name: "updated color name",
                    fruits: {{
                        set: [ {{ id: {fruit_id_gql} }} ]
                        add: [ {{ id: {fruit_id_gql} }} ]
                    }}
                }}
            ) {{
                id
                name
                fruits {{
                    id
                }}
            }}
        }}
        """,
            id="add",
        ),
        pytest.param(
            """
        mutation {{
            updateColor(
                data: {{
                    id: {color_id_gql},
                    name: "updated color name",
                    fruits: {{
                        set: [ {{ id: {fruit_id_gql} }} ]
                        create: [ {{ name: "new fruit 3 during update", adjectives: ["baz"] }} ]
                    }}
                }}
            ) {{
                id
                name
                fruits {{
                    id
                }}
            }}
        }}
        """,
            id="create",
        ),
        pytest.param(
            """
        mutation {{
            updateColor(
                data: {{
                    id: {color_id_gql},
                    name: "updated color name",
                    fruits: {{
                        set: [ {{ id: {fruit_id_gql} }} ]
                        remove: [ {{ id: {fruit_id_gql} }} ]
                    }}
                }}
            ) {{
                id
                name
                fruits {{
                    id
                }}
            }}
        }}
        """,
            id="remove",
        ),
    ],
)
async def test_update_with_to_many_set_exclusive_with_add_create_remove(
    query: str, raw_colors: RawRecordData, raw_fruits: RawRecordData, any_query: AnyQueryExecutor
) -> None:
    """Tests updating a record and setting (replacing) a to-many relationship."""
    color_id_gql = to_graphql_representation(raw_colors[0]["id"], "input")
    # Use a different fruit to test the update
    fruit_id_gql = to_graphql_representation(raw_fruits[1]["id"], "input")
    result = await maybe_async(any_query(query.format(color_id_gql=color_id_gql, fruit_id_gql=fruit_id_gql)))
    assert not result.data
    assert result.errors
    assert len(result.errors) == 1
    assert (
        result.errors[0].args[0] == "You cannot use `set` with `create`, `add` or `remove` in a -to-many relation input"
    )


@pytest.mark.snapshot
async def test_update_with_nested_mixed_relations_create(
    raw_farms: RawRecordData,
    raw_fruits: RawRecordData,
    raw_colors: RawRecordData,
    any_query: AnyQueryExecutor,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:
    """Tests updating a record and creating multiple nested relations with different structures."""
    color_id_gql = to_graphql_representation(raw_colors[0]["id"], "input")
    query = f"""
        mutation {{
            updateColor(
                data: {{
                    id: {color_id_gql},
                    name: "Updated White 2",
                    fruits: {{
                        create: [
                            {{
                                name: "New Grape 2",
                                product: {{ create: {{ name: "juice" }} }},
                                adjectives: ["sweet"]
                            }},
                            {{
                                name: "New Lychee 2",
                                farms: {{ create: [ {{ name: "Organic farm" }} ] }},
                                adjectives: ["exotic"]
                            }},
                        ]
                    }}
                }}
            ) {{
                id
                name
                fruits {{
                    name
                    product {{ name }}
                    farms {{ name }}
                }}
            }}
        }}
    """
    result = await maybe_async(any_query(query))
    assert not result.errors
    assert result.data
    # Sort fruits for assertion stability
    fruits_data = sorted(result.data["updateColor"]["fruits"], key=lambda x: x["name"])
    assert result.data["updateColor"]["id"] == to_graphql_representation(raw_colors[0]["id"], "output")
    assert result.data["updateColor"]["name"] == "Updated White 2"
    assert fruits_data == [
        # Existing fruit
        {
            "name": raw_fruits[0]["name"],
            "farms": [
                {
                    "name": to_graphql_representation(farm["name"], "output")  # noqa: B035
                    for farm in raw_farms
                    if farm["fruit_id"] == raw_fruits[0]["id"]
                }
            ],
            "product": None,
        },
        {"name": "New Grape 2", "product": {"name": "juice"}, "farms": []},
        {"name": "New Lychee 2", "product": None, "farms": [{"name": "Organic farm"}]},
    ]

    # Heterogeneous params means inserts cannot be batched
    query_tracker.assert_statements(4, "insert", sql_snapshot)  # product, farm, fruit1, fruit2
    query_tracker.assert_statements(1, "update", sql_snapshot)  # update color name
    query_tracker.assert_statements(1, "select", sql_snapshot)  # fetch updated color + new relations


@pytest.mark.snapshot
async def test_update_many(
    raw_colors: RawRecordData, any_query: AnyQueryExecutor, query_tracker: QueryTracker, sql_snapshot: SnapshotAssertion
) -> None:
    """Tests updating multiple records in a single mutation."""
    color_id1_gql = to_graphql_representation(raw_colors[0]["id"], "input")
    color_id2_gql = to_graphql_representation(raw_colors[1]["id"], "input")
    query = f"""
        mutation {{
            updateColors(
                data: [
                    {{ id: {color_id1_gql}, name: "batch updated color" }},
                    {{ id: {color_id2_gql}, name: "batch updated color" }}
                ]
            ) {{
                id
                name
            }}
        }}
    """
    result = await maybe_async(any_query(query))
    assert not result.errors
    assert result.data
    # Order might not be guaranteed, sort by ID
    updated_colors = sorted(result.data["updateColors"], key=lambda x: x["id"])
    expected_colors = sorted(
        [
            {"id": to_graphql_representation(raw_colors[0]["id"], "output"), "name": "batch updated color"},
            {"id": to_graphql_representation(raw_colors[1]["id"], "output"), "name": "batch updated color"},
        ],
        key=lambda x: x["id"],
    )
    assert updated_colors == expected_colors

    query_tracker.assert_statements(1, "update", sql_snapshot)  # Update colors in a single query
    query_tracker.assert_statements(1, "select", sql_snapshot)  # Fetch updated records


# Delete


@pytest.mark.snapshot
async def test_delete_filter(
    raw_users: RawRecordData,
    raw_groups: RawRecordData,
    any_query: AnyQueryExecutor,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:
    query = """
        mutation {
            deleteUsersFilter(
                filter: {
                    name: { eq: "Alice" }
                }
            ) {
                id
                name
                group {
                    name
                }
            }
        }
    """
    result = await maybe_async(any_query(query))
    assert not result.errors
    assert result.data
    assert len(result.data["deleteUsersFilter"]) == 1
    apple_fruit = next(fruit for fruit in raw_users if fruit["name"] == "Alice")
    assert result.data["deleteUsersFilter"] == [
        {"id": apple_fruit["id"], "name": "Alice", "group": {"name": raw_groups[0]["name"]}}
    ]

    query_tracker.assert_statements(1, "select", sql_snapshot)
    query_tracker.assert_statements(1, "delete", sql_snapshot)


@pytest.mark.snapshot
async def test_delete_all(
    raw_users: RawRecordData, any_query: AnyQueryExecutor, query_tracker: QueryTracker, sql_snapshot: SnapshotAssertion
) -> None:
    query = """
        mutation {
            deleteUsers {
                id
                name
                group {
                    name
                }
            }
        }
    """
    result = await maybe_async(any_query(query))
    assert not result.errors
    assert result.data
    assert len(result.data["deleteUsers"]) == len(raw_users)
    query_tracker.assert_statements(1, "select", sql_snapshot)
    query_tracker.assert_statements(1, "delete", sql_snapshot)


# Custom mutations


@pytest.mark.snapshot
async def test_column_override(
    any_query: AnyQueryExecutor, query_tracker: QueryTracker, sql_snapshot: SnapshotAssertion
) -> None:
    query = """
        mutation {
            createBlueColor(data: { name: "Green" }) {
                name
            }
        }
    """
    result = await maybe_async(any_query(query))
    assert not result.errors
    assert result.data
    assert result.data["createBlueColor"] == {"name": "Blue"}
    query_tracker.assert_statements(1, "insert", sql_snapshot)
    query_tracker.assert_statements(1, "select", sql_snapshot)


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
async def test_read_only_column_override(query_name: str, query: str, any_query: AnyQueryExecutor) -> None:
    result = await maybe_async(any_query(query))
    assert not result.errors
    assert result.data
    assert result.data[query_name] == {"name": "batman", "rank": 1}


@pytest.mark.parametrize(
    ("query_name", "query"),
    [
        pytest.param(
            "createAppleColor",
            """
                mutation {
                    createAppleColor(data: { name: "Red" }) {
                        name
                        fruits {
                            name
                        }
                    }
                }
                """,
            id="not-existing",
        ),
        pytest.param(
            "createColorForExistingFruits",
            """
                mutation {
                    createColorForExistingFruits(data: { name: "Red" }) {
                        name
                        fruits {
                            name
                        }
                    }
                }
                """,
            id="existing",
        ),
    ],
)
async def test_relationship_to_many_override(query_name: str, query: str, any_query: AnyQueryExecutor) -> None:
    result = await maybe_async(any_query(query))
    assert not result.errors
    assert result.data
    assert result.data[query_name] == {"name": "Red", "fruits": [{"name": "Apple"}, {"name": "Strawberry"}]}


@pytest.mark.parametrize(
    ("query_name", "query"),
    [
        pytest.param(
            "createRedFruit",
            """
            mutation {
                createRedFruit(data: { name: "Apple", adjectives: ["juicy"] }) {
                    name
                    color {
                        name
                    }
                }
            }
            """,
            id="not-existing",
        ),
        pytest.param(
            "createFruitForExistingColor",
            """
            mutation {
                createFruitForExistingColor(data: { name: "Apple", adjectives: ["juicy"] }) {
                    name
                    color {
                        name
                    }
                }
            }
            """,
            id="existing",
        ),
    ],
)
async def test_relationship_to_one_override(query_name: str, query: str, any_query: AnyQueryExecutor) -> None:
    result = await maybe_async(any_query(query))
    assert not result.errors
    assert result.data
    assert result.data[query_name] == {"name": "Apple", "color": {"name": "Red"}}
