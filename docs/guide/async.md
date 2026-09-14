# Async Support

Strawchemy supports both synchronous and asynchronous operations. You can use either `StrawchemySyncRepository` or
`StrawchemyAsyncRepository` depending on your needs:

```python
from strawchemy import StrawchemySyncRepository, StrawchemyAsyncRepository


# Synchronous resolver
@strawchemy.field
def get_color(self, info: strawberry.Info, color: str) -> ColorType | None:
    repo = StrawchemySyncRepository(ColorType, info, filter_statement=select(Color).where(Color.name == color))
    return repo.get_one_or_none().graphql_type_or_none()


# Asynchronous resolver
@strawchemy.field
async def get_color(self, info: strawberry.Info, color: str) -> ColorType | None:
    repo = StrawchemyAsyncRepository(ColorType, info, filter_statement=select(Color).where(Color.name == color))
    return await repo.get_one_or_none().graphql_type_or_none()


# Synchronous mutation
@strawberry.type
class Mutation:
    create_user: UserType = strawchemy.create(UserCreateInput, repository_type=StrawchemySyncRepository)


# Asynchronous mutation
@strawberry.type
class AsyncMutation:
    create_user: UserType = strawchemy.create(UserCreateInput, repository_type=StrawchemyAsyncRepository)
```

By default, Strawchemy uses the StrawchemySyncRepository as its repository type. You can override this behavior by
specifying a different repository using the `repository_type` configuration option.
