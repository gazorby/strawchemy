# Create Mutations

Create mutations allow you to insert new records into your database. Strawchemy provides two types of create mutations:

1. **Single entity creation**: Creates a single record
2. **Batch creation**: Creates multiple records in a single operation

<details>
<summary>Create mutation examples</summary>

## Basic Create Mutation

```python
# Define input type for creation
@strawchemy.input(Color, include=["name"])
class ColorCreateInput:
    pass


@strawberry.type
class Mutation:
    # Single entity creation
    create_color: ColorType = strawchemy.create(ColorCreateInput)

    # Batch creation
    create_colors: list[ColorType] = strawchemy.create(ColorCreateInput)
```

GraphQL usage:

```graphql
# Create a single color
mutation {
    createColor(data: { name: "Purple" }) {
        id
        name
    }
}

# Create multiple colors in one operation
mutation {
    createColors(data: [{ name: "Teal" }, { name: "Magenta" }]) {
        id
        name
    }
}
```

</details>
