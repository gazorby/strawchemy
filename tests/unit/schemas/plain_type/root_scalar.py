import strawberry

from strawchemy import Strawchemy

strawchemy = Strawchemy("postgresql")


@strawberry.type
class Query:
    plain: int = strawchemy.field()
