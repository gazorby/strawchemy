from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from pytest_lazy_fixtures import lf
from strawchemy import StrawchemySyncRepository

from tests.integration.models import User

if TYPE_CHECKING:
    from pytest_codspeed import BenchmarkFixture
    from strawchemy import Strawchemy


@pytest.mark.benchmark(group="schema")
@pytest.mark.parametrize("strawchemy", [lf("strawchemy_postgresql"), lf("strawchemy_sqlite"), lf("strawchemy_mysql")])
def test_build_user_type(strawchemy: Strawchemy) -> None:
    strawchemy.type(User, include="all", override=True)(type("UserType", (), {}))


@pytest.mark.benchmark(group="schema")
@pytest.mark.parametrize("strawchemy", [lf("strawchemy_postgresql"), lf("strawchemy_sqlite"), lf("strawchemy_mysql")])
def test_build_user_filter(strawchemy: Strawchemy) -> None:
    strawchemy.filter(User, include="all", override=True)(type("UserFilter", (), {}))


@pytest.mark.benchmark(group="schema")
@pytest.mark.parametrize("strawchemy", [lf("strawchemy_postgresql"), lf("strawchemy_sqlite"), lf("strawchemy_mysql")])
def test_build_user_create_input(strawchemy: Strawchemy) -> None:
    strawchemy.create_input(User, include="all", override=True)(type("UserFilter", (), {}))


@pytest.mark.benchmark(group="schema")
@pytest.mark.parametrize("strawchemy", [lf("strawchemy_postgresql"), lf("strawchemy_sqlite"), lf("strawchemy_mysql")])
def test_build_user_pk_update_input(strawchemy: Strawchemy) -> None:
    strawchemy.create_input(User, include="all", override=True)(type("UserFilter", (), {}))


@pytest.mark.benchmark(group="schema")
@pytest.mark.parametrize("strawchemy", [lf("strawchemy_postgresql"), lf("strawchemy_sqlite"), lf("strawchemy_mysql")])
def test_build_user_query_field(strawchemy: Strawchemy, benchmark: BenchmarkFixture) -> None:
    @strawchemy.filter(User, include="all", override=True)
    class UserFilter: ...

    @strawchemy.order(User, include="all", override=True)
    class UserOrderBy: ...

    @strawchemy.distinct_on(User, include="all", override=True)
    class UserDistinctOn: ...

    benchmark(
        lambda: strawchemy.field(
            filter_input=UserFilter,
            order_by=UserOrderBy,
            distinct_on=UserDistinctOn,
            repository_type=StrawchemySyncRepository,
        )
    )
