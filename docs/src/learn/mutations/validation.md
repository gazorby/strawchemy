# Validation

A mutation can validate its input with a Pydantic model before writing to the database, and return the failures to the client as data.

## Validating input

Declare a Pydantic model with `@strawchemy.pydantic.create` — or `.pk_update`/`.filter_update` for
the other mutation shapes — and pass it as `validation` to the mutation field. The field's return
type becomes a union of the mutated type and `ValidationErrorType`, so a validation failure comes
back as data instead of raising:

```python
from typing import Annotated

from pydantic import AfterValidator
from strawchemy import ValidationErrorType
from strawchemy.validation.pydantic import PydanticValidation


def _check_lower_case(value: str) -> str:
    if not value.islower():
        raise ValueError("Title must be lower cased")
    return value


@strawchemy.pydantic.create(Tag, include="all", exclude=["id"])
class TagCreateValidation:
    name: Annotated[str, AfterValidator(_check_lower_case)]


@strawchemy.pydantic.create(Post, include="all", exclude=["id"])
class PostCreateValidation:
    title: Annotated[str, AfterValidator(_check_lower_case)]
    tags: list[TagCreateValidation] | None = strawberry.UNSET


@strawberry.type
class Mutation:
    create_validated_post: PostType | ValidationErrorType = strawchemy.create(
        PostCreateInput, validation=PydanticValidation(PostCreateValidation)
    )
```

Both models exclude `id` because `PostCreateInput` never provides one. With `include="all"` and
no exclusion, `id` would be a required pydantic field, and validation would reject every call
with `id: Field required` before it checks `title`. `tags` mirrors the
shape a relationship-carrying create input would send, but `PostCreateInput` has no `tags` field,
so this mutation never reaches that branch.

The generated model inherits from the decorated class, so validators declared in its body —
`@field_validator`, `@model_validator` — run as well, and its methods stay available:

```python
from pydantic import field_validator


@strawchemy.pydantic.create(Tag, include=["name"])
class TagCreateValidation:
    @field_validator("name")
    @classmethod
    def check_lower_case(cls, value: str) -> str:
        return _check_lower_case(value)
```

::: warning
Add `ValidationErrorType` to the mutation field's return union, as in `PostType | ValidationErrorType` above. Without it, a validation failure still returns a `ValidationErrorType`, which the field's declared type cannot resolve: the client gets an execution error, such as `'ValidationErrorType' object has no attribute 'title'`, instead of the validation errors.
:::

## What the client receives

A failed validation returns a `ValidationErrorType` with the underlying pydantic error details
instead of the created record:

```graphql
mutation {
    createValidatedPost(data: { title: "Bad Title", content: "...", views: 0 }) {
        __typename
        ... on PostType {
            title
        }
        ... on ValidationErrorType {
            id
            errors {
                id
                loc
                message
                type
            }
        }
    }
}
```

```json
{
  "data": {
    "createValidatedPost": {
      "__typename": "ValidationErrorType",
      "id": "ERROR",
      "errors": [
        {
          "id": "ERROR",
          "loc": ["title"],
          "message": "Value error, Title must be lower cased",
          "type": "value_error"
        }
      ]
    }
  }
}
```
