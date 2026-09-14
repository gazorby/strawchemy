# Delete Mutations

Delete mutations allow you to remove records from your database. Strawchemy provides two types of delete mutations:

1. **Delete all**: Removes all records of a specific type
2. **Delete with filter**: Removes records that match a filter condition

<details>
<summary>Delete mutation examples</summary>

```python
@strawchemy.filter(User, include="all")
class UserFilter:
    pass


@strawberry.type
class Mutation:
    # Delete all users
    delete_users: list[UserType] = strawchemy.delete()

    # Delete users that match a filter
    delete_users_filter: list[UserType] = strawchemy.delete(UserFilter)
```

GraphQL usage:

```graphql
# Delete all users
mutation {
    deleteUsers {
        id
        name
    }
}

# Delete users that match a filter
mutation {
    deleteUsersFilter(filter: { name: { eq: "Alice" } }) {
        id
        name
    }
}
```

The returned data contains the records that were deleted.

</details>
