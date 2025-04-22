from __future__ import annotations

from typing import Annotated

from pydantic import AfterValidator
from strawchemy import Strawchemy, ValidationErrorType

import strawberry
from tests.unit.models import User

strawchemy = Strawchemy()


def _check_lower_case(value: str) -> str:
    if not value.islower():
        msg = "Name must be lower cased"
        raise ValueError(msg)
    return value


@strawchemy.create_validation(User, include="all")
class UserCreateValidation:
    name: Annotated[str, AfterValidator(_check_lower_case)]


@strawchemy.pk_update_validation(User, include="all")
class UserPkUpdateValidation:
    name: Annotated[str, AfterValidator(_check_lower_case)]


@strawchemy.filter_update_validation(User, include="all")
class UserFilterValidation:
    name: Annotated[str, AfterValidator(_check_lower_case)]


@strawchemy.create_input(User, include="all")
class UserCreate: ...


@strawchemy.filter_update_input(User, include="all")
class UserUpdate: ...


@strawchemy.pk_update_input(User, include="all")
class UserPkUpdate: ...


@strawchemy.type(User, include="all")
class UserType: ...


@strawchemy.filter(User, include="all")
class UserFilter: ...


@strawberry.type
class Mutation:
    create_user: UserType | ValidationErrorType = strawchemy.create(UserCreate, validation=UserCreateValidation)
    update_users: list[UserType | ValidationErrorType] = strawchemy.update(
        UserUpdate, filter_input=UserFilter, validation=UserFilterValidation
    )
    update_user_by_id: UserType | ValidationErrorType = strawchemy.update_by_ids(
        UserPkUpdate, validation=UserPkUpdateValidation
    )
    update_user_by_ids: list[UserType | ValidationErrorType] = strawchemy.update_by_ids(
        UserPkUpdate, validation=UserPkUpdateValidation
    )
