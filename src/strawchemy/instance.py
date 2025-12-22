from __future__ import annotations

from typing import Annotated, TypeVar

from strawberry.types.private import StrawberryPrivate

__all__ = ("MapperModelInstance", "ModelInstance")

T = TypeVar("T")


class MapperModelInstance(StrawberryPrivate): ...


ModelInstance = Annotated[T, MapperModelInstance()]
"""When defined on a strawchemy type, it allows accessing the model instance in resolvers.

```python
@strawchemy.type(User)
class UserObjectType:
    instance: ModelInstance

    @strawberry.field
    def name(self) -> str:
        return f"Hello, {self.first_name} {self.last_name}"
```
"""
