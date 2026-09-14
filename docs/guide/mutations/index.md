# Mutations

Strawchemy provides a powerful way to create GraphQL mutations for your SQLAlchemy models. These mutations allow you to
create, update, and delete data through your GraphQL API.

<details>
<summary>Mutations example</summary>

```python
import strawberry
from strawchemy import Strawchemy, StrawchemySyncRepository, StrawchemyAsyncRepository

# Initialize the strawchemy mapper
strawchemy = Strawchemy("postgresql")


# Define input types for mutations
@strawchemy.input(User, include=["name", "email"])
class UserCreateInput:
    pass


@strawchemy.input(User, include=["id", "name", "email"])
class UserUpdateInput:
    pass


@strawchemy.filter(User, include="all")
class UserFilter:
    pass


# Define GraphQL mutation fields
@strawberry.type
class Mutation:
    # Create mutations
    create_user: UserType = strawchemy.create(UserCreateInput)
    create_users: list[UserType] = strawchemy.create(UserCreateInput)  # Batch creation

    # Update mutations
    update_user: UserType = strawchemy.update_by_ids(UserUpdateInput)
    update_users: list[UserType] = strawchemy.update_by_ids(UserUpdateInput)  # Batch update
    update_users_filter: list[UserType] = strawchemy.update(UserUpdateInput, UserFilter)  # Update with filter

    # Delete mutations
    delete_users: list[UserType] = strawchemy.delete()  # Delete all
    delete_users_filter: list[UserType] = strawchemy.delete(UserFilter)  # Delete with filter


# Create schema with mutations
schema = strawberry.Schema(query=Query, mutation=Mutation)
```

</details>
