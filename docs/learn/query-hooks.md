# Query hooks

A query hook reaches into the statement Strawchemy is already building, either to constrain what it returns or to load data the client's selection did not ask for. It attaches to a type, where it applies to every query against that type, or to a single field.

## Base filter

A `QueryHook` subclass overriding `apply_hook` applies to every query against a type, unlike a `filter_statement` written into a single [resolver](/learn/resolvers) — so `PublishedPostType` can only ever return published posts, however it's queried:

```python
from strawchemy import QueryHook
from sqlalchemy import Select
from sqlalchemy.orm.util import AliasedClass


class PublishedPostsHook(QueryHook[Post]):
    def apply_hook(self, statement: Select[tuple[Post]], alias: AliasedClass[Post]) -> Select[tuple[Post]]:
        return statement.where(alias.published_at.is_not(None))


@strawchemy.type(Post, exclude={"content"}, query_hook=PublishedPostsHook())
class PublishedPostType:
    pass
```

Pass a `QueryHook` instance to `@strawchemy.field`'s `query_hook` argument instead of `@strawchemy.type`'s to apply it to one field rather than every query for the type.

::: warning
When implementing `apply_hook`:

- You must use the provided `alias` parameter to refer to columns of the model on which the hook is applied. Otherwise,
  the statement may fail.
- The GraphQL context is available through `self.info` within hook methods.
- You must set a `ModelInstance` typed attribute if you want to access the model instance values.
  The `instance` attribute is matched by the `ModelInstance[Post]` type hint, so you can give it any name you want.
:::

## Loading extra data

`apply_hook` returns the statement unchanged by default — loading columns or relationships doesn't go through it at all. A `QueryHook`'s `load` parameter loads them instead, even when the GraphQL query didn't request them — needed whenever a custom `@strawchemy.field` reads model attributes the query selection wouldn't otherwise touch, such as a computed `summary` field built from `title` and `views`:

```python
from strawchemy import ModelInstance, QueryHook


@strawchemy.type(Post, exclude={"content"})
class PostTypeWithSummary:
    instance: ModelInstance[Post]

    @strawchemy.field(query_hook=QueryHook(load=[Post.title, Post.views]))
    def summary(self) -> str:
        return f"{self.instance.title} ({self.instance.views} views)"
```

`load` accepts four shapes:

- Specific columns, as a list of attributes — loads exactly `title` and `views`, as above.
- A bare relationship attribute — loads `tags` in full, without specifying which of its columns:

  ```python
  @strawchemy.field(query_hook=QueryHook(load=[Post.tags]))
  def tag_names(self) -> str:
      return ", ".join(tag.name for tag in self.instance.tags)
  ```

- A `(relationship, columns)` tuple — loads only `name` off `author`, not the rest of `User`:

  ```python
  @strawchemy.field(query_hook=QueryHook(load=[(Post.author, [User.name])]))
  def author_name(self) -> str:
      return self.instance.author.name if self.instance.author else "No author!"
  ```

- Nested tuples — loads relationships several levels deep, here `tags` on every post in `posts`:

  ```python
  @strawchemy.field(query_hook=QueryHook(load=[(User.posts, [(Post.tags, [Tag.name])])]))
  def all_tag_names(self) -> str:
      return ", ".join(tag.name for post in self.instance.posts for tag in post.tags)
  ```
