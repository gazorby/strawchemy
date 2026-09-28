import strawberry

from strawchemy import Strawchemy

strawchemy = Strawchemy("postgresql")


@strawberry.type
class Plain:
    name: str


@strawberry.type
class Mutation:
    plain: list[Plain] = strawchemy.delete()
