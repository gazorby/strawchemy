# Working with Relationships in Create Mutations

Strawchemy supports creating entities with relationships. You can:

1. **Set existing relationships**: Link to existing records
2. **Create nested relationships**: Create related records in the same mutation
3. **Set to null**: Remove relationships

<details>
<summary>Create with relationships examples</summary>

## To-One Relationships

```python
@strawchemy.input(Fruit, include=["name", "adjectives"])
class FruitCreateInput:
    # Define relationship inputs
    color: auto  # 'auto' will generate appropriate relationship inputs
```

GraphQL usage:

```graphql
# Set an existing relationship
mutation {
    createFruit(
        data: {
            name: "Apple"
            adjectives: ["sweet", "crunchy"]
            color: { set: { id: "123e4567-e89b-12d3-a456-426614174000" } }
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
    createFruit(
        data: {
            name: "Banana"
            adjectives: ["yellow", "soft"]
            color: { create: { name: "Yellow" } }
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
    createFruit(
        data: {
            name: "Strawberry"
            adjectives: ["red", "sweet"]
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
@strawchemy.input(Color, include=["name"])
class ColorCreateInput:
    # Define to-many relationship inputs
    fruits: auto  # 'auto' will generate appropriate relationship inputs
```

GraphQL usage:

```graphql
# Set existing to-many relationships
mutation {
    createColor(
        data: {
            name: "Red"
            fruits: { set: [{ id: "123e4567-e89b-12d3-a456-426614174000" }] }
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
    createColor(
        data: {
            name: "Green"
            fruits: { add: [{ id: "123e4567-e89b-12d3-a456-426614174000" }] }
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
    createColor(
        data: {
            name: "Blue"
            fruits: {
                create: [
                    { name: "Blueberry", adjectives: ["small", "blue"] }
                    { name: "Plum", adjectives: ["juicy", "purple"] }
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

## Nested Relationships

You can create deeply nested relationships:

```graphql
mutation {
    createColor(
        data: {
            name: "White"
            fruits: {
                create: [
                    {
                        name: "Grape"
                        adjectives: ["tangy", "juicy"]
                        farms: { create: [{ name: "Bio farm" }] }
                    }
                ]
            }
        }
    ) {
        name
        fruits {
            name
            farms {
                name
            }
        }
    }
}
```

</details>
