# Update Mutations

Update mutations allow you to modify existing records. Strawchemy provides several types of update mutations:

1. **Update by primary key**: Update a specific record by its ID
2. **Batch update by primary keys**: Update multiple records by their IDs
3. **Update with filter**: Update records that match a filter condition

<details>
<summary>Update mutation examples</summary>

## Basic Update Mutation

```python
# Define input type for updates
@strawchemy.input(Color, include=["id", "name"])
class ColorUpdateInput:
    pass


@strawchemy.filter(Color, include="all")
class ColorFilter:
    pass


@strawberry.type
class Mutation:
    # Update by ID
    update_color: ColorType = strawchemy.update_by_ids(ColorUpdateInput)

    # Batch update by IDs
    update_colors: list[ColorType] = strawchemy.update_by_ids(ColorUpdateInput)

    # Update with filter
    update_colors_filter: list[ColorType] = strawchemy.update(ColorUpdateInput, ColorFilter)
```

GraphQL usage:

```graphql
# Update by ID
mutation {
    updateColor(
        data: { id: "123e4567-e89b-12d3-a456-426614174000", name: "Crimson" }
    ) {
        id
        name
    }
}

# Batch update by IDs
mutation {
    updateColors(
        data: [
            { id: "123e4567-e89b-12d3-a456-426614174000", name: "Crimson" }
            { id: "223e4567-e89b-12d3-a456-426614174000", name: "Navy" }
        ]
    ) {
        id
        name
    }
}

# Update with filter
mutation {
    updateColorsFilter(
        data: { name: "Bright Red" }
        filter: { name: { eq: "Red" } }
    ) {
        id
        name
    }
}
```

</details>
