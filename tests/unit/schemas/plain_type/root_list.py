import strawberry

from strawchemy import Strawchemy

strawchemy = Strawchemy("postgresql")


@strawberry.type
class Plain:
    name: str


@strawberry.type
class Query:
    plain: list[Plain] = strawchemy.field()
