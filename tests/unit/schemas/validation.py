from __future__ import annotations

from typing import Annotated

from pydantic import AfterValidator
from strawchemy import Strawchemy, ValidationErrorType
from strawchemy.dto.pydantic import pydantic_dto
from strawchemy.dto.types import Purpose

import strawberry
from tests.unit.models import User

strawchemy = Strawchemy()


def _check_lower_case(value: str) -> str:
    if not value.islower():
        msg = "Name must be lower cased"
        raise ValueError(msg)
    return value


@pydantic_dto(User, Purpose.WRITE, include="all")
class UserValidation:
    name: Annotated[str, AfterValidator(_check_lower_case)]


@strawchemy.create_input(User, include="all")
class UserCreate: ...


@strawchemy.type(User, include="all")
class UserType: ...


@strawberry.type
class Mutation:
    create_user: UserType | ValidationErrorType = strawchemy.create(UserCreate, validation=UserValidation)
