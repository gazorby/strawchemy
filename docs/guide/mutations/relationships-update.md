# Working with Relationships in Update Mutations

Similar to create mutations, update mutations support modifying relationships:

<details>
<summary>Update with relationships examples</summary>

## To-One Relationships

```python
@strawchemy.input(Fruit, include=["id", "name"])
class FruitUpdateInput:
    # Define relationship inputs
    color: auto
```

GraphQL usage:

```graphql
# Set an existing relationship
mutation {
    updateFruit(
        data: {
            id: "123e4567-e89b-12d3-a456-426614174000"
            name: "Red Apple"
            color: { set: { id: "223e4567-e89b-12d3-a456-426614174000" } }
        }
    ) {
        id
        name
        color {
            id
            name
        }
    }
}

# Create a new related entity
mutation {
    updateFruit(
        data: {
            id: "123e4567-e89b-12d3-a456-426614174000"
            name: "Green Apple"
            color: { create: { name: "Green" } }
        }
    ) {
        id
        name
        color {
            id
            name
        }
    }
}

# Set relationship to null
mutation {
    updateFruit(
        data: {
            id: "123e4567-e89b-12d3-a456-426614174000"
            name: "Plain Apple"
            color: { set: null }
        }
    ) {
        id
        name
        color {
            id
        }
    }
}
```

## To-Many Relationships

```python
@strawchemy.input(Color, include=["id", "name"])
class ColorUpdateInput:
    # Define to-many relationship inputs
    fruits: auto
```

GraphQL usage:

```graphql
# Set (replace) to-many relationships
mutation {
    updateColor(
        data: {
            id: "123e4567-e89b-12d3-a456-426614174000"
            name: "Red"
            fruits: { set: [{ id: "223e4567-e89b-12d3-a456-426614174000" }] }
        }
    ) {
        id
        name
        fruits {
            id
            name
        }
    }
}

# Add to existing to-many relationships
mutation {
    updateColor(
        data: {
            id: "123e4567-e89b-12d3-a456-426614174000"
            name: "Red"
            fruits: { add: [{ id: "223e4567-e89b-12d3-a456-426614174000" }] }
        }
    ) {
        id
        name
        fruits {
            id
            name
        }
    }
}

# Remove from to-many relationships
mutation {
    updateColor(
        data: {
            id: "123e4567-e89b-12d3-a456-426614174000"
            name: "Red"
            fruits: { remove: [{ id: "223e4567-e89b-12d3-a456-426614174000" }] }
        }
    ) {
        id
        name
        fruits {
            id
            name
        }
    }
}

# Create new related entities
mutation {
    updateColor(
        data: {
            id: "123e4567-e89b-12d3-a456-426614174000"
            name: "Red"
            fruits: {
                create: [
                    { name: "Cherry", adjectives: ["small", "red"] }
                    { name: "Strawberry", adjectives: ["sweet", "red"] }
                ]
            }
        }
    ) {
        id
        name
        fruits {
            id
            name
        }
    }
}
```

## Combining Operations

You can combine `add` and `create` operations in a single update:

```graphql
mutation {
    updateColor(
        data: {
            id: "123e4567-e89b-12d3-a456-426614174000"
            name: "Red"
            fruits: {
                add: [{ id: "223e4567-e89b-12d3-a456-426614174000" }]
                create: [{ name: "Raspberry", adjectives: ["tart", "red"] }]
            }
        }
    ) {
        id
        name
        fruits {
            id
            name
        }
    }
}
```

Note: You cannot use `set` with `add`, `remove`, or `create` in the same operation for to-many relationships.

</details>
