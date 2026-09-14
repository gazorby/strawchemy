# Input Validation

Strawchemy supports input validation using Pydantic models. You can define validation schemas and apply them to
mutations to ensure data meets specific requirements before being processed.

Create Pydantic models for the input type where you want the validation, and set the `validation` parameter on
`strawchemy.field`:

<details>
<summary>Validation example</summary>

```python
from models import User, Group
from typing import Annotated
from pydantic import AfterValidator
from strawchemy import InputValidationError, ValidationErrorType
from strawchemy.validation.pydantic import PydanticValidation


def _check_lower_case(value: str) -> str:
    if not value.islower():
        raise ValueError("Name must be lower cased")
    return value


@strawchemy.pydantic.create(Group, include="all")
class GroupCreateValidation:
    name: Annotated[str, AfterValidator(_check_lower_case)]


@strawchemy.pydantic.create(User, include="all")
class UserCreateValidation:
    name: Annotated[str, AfterValidator(_check_lower_case)]
    group: GroupCreateValidation | None = strawberry.UNSET


@strawberry.type
class Mutation:
    create_user: UserType | ValidationErrorType = strawchemy.create(
        UserCreate, validation=PydanticValidation(UserCreateValidation)
    )
```

> To get the validation errors exposed in the schema, you need to add `ValidationErrorType` in the field union type

When validation fails, the query will returns a `ValidationErrorType` with detailed error information from pydantic
validation:

```graphql
mutation {
    createUser(data: { name: "Bob" }) {
        __typename
        ... on UserType {
            name
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
    "createUser": {
      "__typename": "ValidationErrorType",
      "id": "ERROR",
      "errors": [
        {
          "id": "ERROR",
          "loc": [
            "name"
          ],
          "message": "Value error, Name must be lower cased",
          "type": "value_error"
        }
      ]
    }
  }
}
```

Validation also works with nested relationships:

```graphql
mutation {
    createUser(
        data: {
            name: "bob"
            group: {
                create: {
                    name: "Group" # This will be validated
                    tag: { set: { id: "..." } }
                }
            }
        }
    ) {
        __typename
        ... on ValidationErrorType {
            errors {
                loc
                message
            }
        }
    }
}
```

</details>
