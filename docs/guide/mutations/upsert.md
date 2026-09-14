# Upsert Mutations

Upsert mutations provide "insert or update" functionality, allowing you to create new records or update existing ones
based on conflict resolution. This is particularly useful when you want to ensure data exists without worrying about
whether it's already in the database.

Strawchemy supports upsert operations for:

1. **Root-level upserts**: Direct upsert mutations on entities
2. **Relationship upserts**: Upsert operations within relationship mutations

<details>
<summary>Upsert mutation examples</summary>

## Basic Upsert Mutation

First, define the necessary input types and enums:

```python
# Define input type for upsert
@strawchemy.input(Fruit, include=["name", "sweetness", "waterPercent"])
class FruitCreateInput:
    pass


# Define which fields can be updated during upsert
@strawchemy.upsert_update_fields(Fruit, include=["sweetness", "waterPercent"])
class FruitUpsertFields:
    pass


# Define which fields are used for conflict detection
@strawchemy.upsert_conflict_fields(Fruit)
class FruitUpsertConflictFields:
    pass


@strawberry.type
class Mutation:
    # Single entity upsert
    upsert_fruit: FruitType = strawchemy.upsert(
        FruitCreateInput, update_fields=FruitUpsertFields, conflict_fields=FruitUpsertConflictFields
    )

    # Batch upsert
    upsert_fruits: list[FruitType] = strawchemy.upsert(
        FruitCreateInput, update_fields=FruitUpsertFields, conflict_fields=FruitUpsertConflictFields
    )
```

## GraphQL Usage

```graphql
# Upsert a single fruit (will create if name doesn't exist, update if it does)
mutation {
    upsertFruit(
        data: { name: "Apple", sweetness: 8, waterPercent: 0.85 }
        conflictFields: name
    ) {
        id
        name
        sweetness
        waterPercent
    }
}

# Batch upsert multiple fruits
mutation {
    upsertFruits(
        data: [
            { name: "Apple", sweetness: 8, waterPercent: 0.85 }
            { name: "Orange", sweetness: 6, waterPercent: 0.87 }
        ]
        conflictFields: name
    ) {
        id
        name
        sweetness
        waterPercent
    }
}
```

## How Upsert Works

1. **Conflict Detection**: The `conflictFields` parameter specifies which field(s) to check for existing records
2. **Update Fields**: The `updateFields` parameter (optional) specifies which fields should be updated if a conflict is
   found
3. **Database Support**:
    - **PostgreSQL**: Uses `ON CONFLICT DO UPDATE`
    - **MySQL**: Uses `ON DUPLICATE KEY UPDATE`
    - **SQLite**: Uses `ON CONFLICT DO UPDATE`

## Upsert in Relationships

You can also use upsert operations within relationship mutations:

```python
@strawchemy.input(Color, include=["id", "name"])
class ColorUpdateInput:
    fruits: auto  # This will include upsert options for fruits
```

```graphql
# Update a color and upsert related fruits
mutation {
    updateColor(
        data: {
            id: 1
            name: "Bright Red"
            fruits: {
                upsert: {
                    create: [
                        { name: "Cherry", sweetness: 7, waterPercent: 0.87 }
                        { name: "Strawberry", sweetness: 8, waterPercent: 0.91 }
                    ]
                    conflictFields: name
                }
            }
        }
    ) {
        id
        name
        fruits {
            id
            name
            sweetness
        }
    }
}
```

## Upsert Behavior

- **If no conflict**: Creates a new record with all provided data
- **If conflict found**: Updates the existing record with fields specified in `updateFields`
- **Conflict resolution**: Based on unique constraints, primary keys, or specified conflict fields
- **Return value**: Always returns the final state of the record (created or updated)

</details>
