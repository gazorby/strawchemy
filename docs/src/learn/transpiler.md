# Transpiler internals

The transpiler turns one GraphQL query into one SQL statement, and the executor beside it turns the rows back into the objects the GraphQL response needs. Both live in `src/strawchemy/transpiler/`. This page covers the problem they solve, the architecture, how a query becomes SQL, how to add a feature, and the optimizations the design makes possible.

The examples run on a small schema: a `color` has many `fruit`, and a `group` has one `color`. Their SQL is the PostgreSQL output unless stated otherwise, trimmed of the clauses that do not matter to the point.

## Trees in, tables out

A GraphQL query is a tree, and the response has the same shape:

```graphql
{
    colors {
        name
        fruits { name }
    }
}
```

```json
{
    "colors": [
        { "name": "red", "fruits": [{ "name": "apple" }, { "name": "cherry" }] },
        { "name": "green", "fruits": [{ "name": "lime" }] }
    ]
}
```

A SQL query returns a flat table. To read colors and their fruits in one statement, the transpiler joins the two tables, and each color appears once per fruit:

```sql
SELECT color.name, color.id, fruit_1.name, fruit_1.id
  FROM color
  LEFT OUTER JOIN fruit AS fruit_1 ON color.id = fruit_1.color_id
```

| color.name | color.id | fruit_1.name | fruit_1.id |
|---|---|---|---|
| red | 1 | apple | 10 |
| red | 1 | cherry | 11 |
| green | 2 | lime | 12 |

Strawchemy keeps one rule: **one GraphQL request produces one SQL statement.** The database does all the reading in one round trip, and the executor rebuilds the tree from the flat rows.

The join is easy. The hard part is that every argument applies to one node of the tree, while SQL applies its clauses to the whole flat table:

- `colors(limit: 2)` means two colors. A `LIMIT 2` on the table above returns two rows, which is red twice.
- `fruits(orderBy: { sweetness: DESC }, limit: 2)` means the two sweetest fruits of each color, not of the whole table.
- `colors(filter: { fruits: { sweetness: { gt: 5 } } })` means colors with at least one sweet fruit. Filtering the joined rows would also hide the color's other fruits from the selection.
- `fruitsAggregate { count }` needs one value per color, and a `GROUP BY` on the main query would collapse the joined rows.

So the transpiler decides, for every part of the tree, where it belongs in the statement: in the main `FROM`, a subquery, a lateral join, a CTE or an `EXISTS`.

## Architecture

### The journey of a query

```text
GraphQL selection     (strawberry)      GraphQL response
  │                                       ▲
  ▼                                       │
QueryNode tree        (repository)      strawberry types
  │                                       ▲
  ▼                                       │
Level + QueryRequest  (_core)           QueryResult
  │                                       ▲
  ▼                                       │
Pipeline              (_passes)         executor
  │                                       ▲
  ▼                                       │
QueryPlan             (_core)             │
  │                                       │
  ▼                                       │
SELECT                (render) ───────► rows
```

1. The repository reads the Strawberry selection into a **`QueryNode` tree**. Each node is a field: a column, a relation, an aggregate or a computed value. A relation node carries its own arguments.
2. `Transpiler.select_executor` wraps the tree and the root arguments in a **`QueryRequest`**, creates the root **`Level`**, and runs the root **`Pipeline`** on it.
3. The pipeline's **passes** fill in two frozen values, a **`RowSet`** and a **`Projection`**, and the level turns them into a **`QueryPlan`**.
4. `render_plan` builds the SQLAlchemy `Select` from the plan. No other code builds the final statement.
5. The **executor** runs it and regroups the flat rows into objects, one collection per relation node and parent.

### Levels

A **level** is one SQL scope: a `FROM` clause with its own `WHERE`, `ORDER BY` and `LIMIT`. The root of the query is always a level. Below it, the transpiler cuts the tree wherever a node needs rows chosen independently of its parent:

```text
colors(limit: 2)
│     root level; paged, so wrapped in a subquery
├── name
├── fruits { name }
│     relation without arguments: a plain join in the root
├── sweetest: fruits(orderBy, limit: 2)
│     relation level of its own: lateral join or ranked CTE
└── fruitsAggregate { count }
      aggregate join: grouped lateral or grouped CTE

filter: { fruits: { sweetness: gt 5 } }
      EXISTS level, correlated to the root
```

Each of the four kinds of level has its own pipeline:

| Kind | Stands for | Becomes |
|---|---|---|
| `root` | the field the client queried | the main statement, or a page subquery when paginated |
| `relation` | a selected relation | a plain join, a lateral join or a ranked CTE |
| `exists` | a filter on a to-many relation | an `EXISTS (...)` predicate in the parent's `WHERE` |
| `dml` | the filter of an `UPDATE` or `DELETE` | `WHERE` predicates on the table |

A level never builds SQL. It offers **services** that read columns and add joins — `column`, `path_column`, `aggregate`, `plan_child`, `plan_exists` and `materialize`, among others — and it knows its parent, so a child level can reuse what its ancestors already joined.

### Two stages: which rows, then what to read

Every level answers two questions, in order:

1. **Rows stage: which rows?** Filter, ordering, `DISTINCT ON`, limit and offset, and the query hooks that restrict rows.
2. **Projection stage: what is read from those rows?** Columns, relations, aggregates and JSON extractions.

Each stage builds one frozen value:

- **`RowSet`** holds the source alias, its joins, `WHERE` predicates, `ORDER BY` terms, `DISTINCT ON`, limit, offset, and the query hooks' statement edits.
- **`Projection`** holds the entities to load, the columns to select, the projection's joins, and the maps the executor reads results with.

Neither builds SQL. Every change returns a new value, so no function can alter what another one already planned.

The split matters because the two stages need different things from SQL. In `colors(limit: 2) { fruits { name } }`, the limit belongs to the rows stage and must count colors; the fruit join belongs to the projection stage and must not be counted. Keeping them apart lets the level decide afterwards how to combine them.

### Passes and pipelines

Each feature of the query language is a **pass**: one class with one method per stage.

```python
class Pass(Protocol):
    def rows(self, level: Level, rows: RowSet) -> RowSet: ...
    def project(self, level: Level, rows: RowSet, projection: Projection) -> Projection: ...
```

A pass reads its part of `level.request` and returns a new `RowSet` or `Projection`. `Filtering` adds `WHERE` predicates, `Ordering` adds `ORDER BY` terms, `OffsetPagination` sets the limit and offset, `Relations` plans the selected relations. A pass that acts on one stage subclasses `PassBase`, which returns the other stage's input unchanged.

A **pipeline** is a tuple of passes and one loop. Every rows stage runs before any projection stage, so a projection sees the finished `RowSet` and can reuse its joins:

```python
def plan(self, level: Level) -> QueryPlan:
    rows = RowSet.over(level.alias)
    for pass_ in self.passes:
        rows = pass_.rows(level, rows)

    projection = Projection.over(level.node, level.alias)
    for pass_ in self.passes:
        projection = pass_.project(level, rows, projection)

    return level.materialize(rows, projection)
```

`_passes/__init__.py` assembles the four pipelines:

```python
DEFAULT_PIPELINES = Pipelines(
    root=Pipeline(
        (
            UserStatement(),
            QueryHooks(),
            Filtering(),
            Ordering(),
            DistinctOn(),
            OffsetPagination(),
            Selection(),
            Relations(),
            Aggregations(),
            RootAggregations(),
        )
    ),
    relation=Pipeline(
        (QueryHooks(), Ordering(), DistinctOn(), OffsetPagination(), Selection(), Relations(), Aggregations())
    ),
    exists=Pipeline((Filtering(),)),
    dml=Pipeline((UserStatement(), Filtering())),
)
```

The order of the passes carries no meaning. `ORDER BY` terms carry a priority — `HOOK`, `CLIENT`, then `DETERMINISTIC` — and the renderer sorts them, so `Ordering` and `QueryHooks` produce the same SQL in either order.

| Pass | Stage | What it does |
|---|---|---|
| `UserStatement` | rows | restricts the root to the field's `filter_statement` |
| `QueryHooks` | both | applies query hooks: statement edits on the rows, column and relationship loads on the projection |
| `Filtering` | rows | turns the filter into `WHERE` predicates, joins and `EXISTS` subqueries |
| `Ordering` | rows | client ordering, else the default ordering, then primary keys for a stable order |
| `DistinctOn` | rows | sets `DISTINCT ON` |
| `OffsetPagination` | rows | sets limit and offset |
| `Selection` | project | loads the selected columns and JSON extractions |
| `Relations` | project | plans each selected relation as a child level and joins it |
| `Aggregations` | project | selects relation aggregates (`fruitsAggregate { count }`) |
| `RootAggregations` | project | window functions for aggregates over the whole result |

### Inline or wrap

After both stages, `Level.materialize` makes the one structural decision of the transpiler: can the rows stage share the projection's `FROM` clause, or must it become a subquery?

The rows stage stays **inline** when it only filters and orders. Its `WHERE` and `ORDER BY` go into the main statement, next to the projection's joins:

```graphql
{ colors(filter: { name: { startswith: "r" } }, orderBy: { name: ASC }) { name fruits { name } } }
```

```sql
SELECT color.name, color.id, fruit_1.name, fruit_1.id
  FROM color
  LEFT OUTER JOIN fruit AS fruit_1 ON color.id = fruit_1.color_id   -- projection stage
 WHERE color.name LIKE 'r%'                                          -- rows stage
 ORDER BY color.name ASC, fruit_1.id ASC
```

With a limit, inlining would count color × fruit rows, so `materialize` **wraps** the rows stage in a subquery and moves the projection onto it:

```graphql
{ colorsPaginated(limit: 2, filter: { name: { startswith: "r" } }, orderBy: { name: ASC }) { name fruits { name } } }
```

```sql
SELECT color.name, color.id, fruit_1.name, fruit_1.id
  FROM (
        SELECT color.name AS name, color.id AS id
          FROM color
         WHERE color.name LIKE 'r%'
         ORDER BY color.name ASC
         LIMIT 2
       ) AS color
  LEFT OUTER JOIN fruit AS fruit_1 ON color.id = fruit_1.color_id
 ORDER BY color.name ASC, fruit_1.id ASC
```

No pass asked for the subquery: `OffsetPagination` set `limit = 2`, and `materialize` saw the limit and wrapped. The subquery exports exactly the columns the projection reads — `name` for the selection, `id` for the fruit join — because `materialize` walks the projection to collect them.

For a relation level, the same decision picks between a plain join and a lateral join or ranked CTE.

## From a tree to one statement

### Relations without arguments

A relation without arguments reads every related row. `Relations` calls `level.plan_child(node, ...)`, which plans the relation on the relation pipeline. Its rows stage stays empty, so `materialize` folds it into the parent as a `LEFT OUTER JOIN` and merges its projection into the parent's. `groups { color { fruits { name } } }` is two joins in one `FROM`.

### Relations with their own rows

`fruits(orderBy: { sweetness: DESC }, limit: 2)` needs the two sweetest fruits of each color. The relation level's rows stage now holds an `ORDER BY` and a limit, so `materialize` hands it to `attach_rows`, which has two strategies.

On PostgreSQL, the child is a lateral subquery, evaluated once per parent row and correlated on the relationship:

```sql
SELECT color.name, color.id, anon_1.name, anon_1.id
  FROM color
  LEFT OUTER JOIN LATERAL (
        SELECT fruit_1.name, fruit_1.id, fruit_1.sweetness
          FROM fruit AS fruit_1
         WHERE color.id = fruit_1.color_id          -- correlation: the current color
         ORDER BY fruit_1.sweetness DESC
         LIMIT 2
       ) AS anon_1 ON TRUE
 ORDER BY color.id ASC, anon_1.sweetness DESC
```

On SQLite and MySQL, which lack lateral joins, the child is a CTE that ranks every fruit within its color, and the join keeps the ranks of the page:

```sql
WITH anon_1 AS (
  SELECT fruit_1.name, fruit_1.id, fruit_1.color_id, fruit_1.sweetness,
         dense_rank() OVER (PARTITION BY fruit_1.color_id
                            ORDER BY fruit_1.sweetness DESC, fruit_1.id) AS rank
    FROM fruit AS fruit_1
)
SELECT color.name, color.id, anon_1.name, anon_1.id
  FROM color
  LEFT OUTER JOIN anon_1
    ON color.id = anon_1.color_id AND anon_1.rank > 0 AND anon_1.rank <= 2
 ORDER BY color.id ASC, anon_1.sweetness DESC
```

Both shapes return the same rows. `attach.py` alone knows about lateral joins and CTEs; it reads `DatabaseFeatures.supports_lateral`, and no other module needs to.

### Filters on to-many relations

`colors(filter: { fruits: { sweetness: { gt: 5 } } }) { name fruits { name } }` asks for colors that have a sweet fruit, with all their fruits. Filtering the fruit join would drop the sour ones from the selection, and a second join in the main `FROM` would repeat each color once per sweet fruit. The filter goes into an `exists` level instead, correlated to the parent:

```sql
SELECT color.name, color.id, fruit_1.name, fruit_1.id
  FROM color
  LEFT OUTER JOIN fruit AS fruit_1 ON color.id = fruit_1.color_id   -- selection: all fruits
 WHERE EXISTS (
        SELECT 1 FROM fruit AS fruit_2                              -- filter: any sweet fruit
         WHERE color.id = fruit_2.color_id AND fruit_2.sweetness > 5
       )
```

`split.py` decides, once per filter, which parts the rows stage tests directly and which go to an `EXISTS`. A filter on a to-one relation cannot multiply rows, so it joins directly; see [To-one filters become inner joins](#to-one-filters-become-inner-joins).

### Aggregates

`fruitsAggregate { count }` needs one count per color. A `GROUP BY` on the main statement would collapse the joined rows, so `attach_grouped` builds a join of its own: a lateral subquery of aggregate functions on PostgreSQL, a CTE grouped by the foreign key elsewhere. It returns one row per parent and never multiplies rows.

### Rebuilding the tree

The executor rebuilds the tree from the flat rows:

- The `SELECT` lists the root entity first, then one entity per relation, so each row holds a color, a fruit, and so on.
- SQLAlchemy's identity map returns one Python object per primary key, so red appears once although it spans two rows.
- For each relation node, the executor collects the related objects per parent object, so the `fruits` of red and of green stay apart.
- Computed values, such as aggregates and JSON extractions, come from labelled columns and are stored under the node that asked for them.

The statement also carries `raiseload("*")`, so reading an attribute the plan did not load raises rather than issuing a query. The repository then walks the `QueryNode` tree once more and builds the Strawberry objects from these collections.

## Adding a feature

### What a new feature touches

A new capability is usually one new pass and one line in `DEFAULT_PIPELINES`. Four properties of the design leave the rest of the code untouched:

1. **Passes do not know each other.** A pass imports `_core` and never another pass; `_core` imports no pass. `tests/unit/transpiler/test_architecture.py` enforces both. Passes interact only through level services and the data those return.
2. **Order does not matter.** `ORDER BY` terms carry priorities and joins are stored under keys, so no pass needs to run before or after another.
3. **Joins are keyed, not counted.** A join is stored under `(kind, node)`, and asking for an existing join returns it. A pass that reads an aggregate another pass already joined gets the same join without coordinating with it.
4. **Structure follows data.** A pass describes what it needs — a limit, an `ORDER BY` term, a `WHERE` predicate — and `materialize` and `attach` decide how to lay it out in SQL. A pass that sets a limit gets the subquery, the lateral join or the ranked CTE without asking for any of them.

### Example: cursor pagination

Relay-style cursor pagination asks for "the 10 colors after `blue`, ordered by name". The pass sets data on the `RowSet` and nothing else:

```python
class CursorPagination(PassBase):
    def rows(self, level: Level, rows: RowSet) -> RowSet:
        request = level.request
        rows = replace(rows, limit=request.limit)
        if request.after is None:
            return rows
        column = level.column(request.after.node)
        return rows.with_where(column > request.after.value)
```

It replaces the offset pass in the root pipeline:

```python
pipelines = replace(
    DEFAULT_PIPELINES,
    root=DEFAULT_PIPELINES.root.replace(OffsetPagination, CursorPagination()),
)
```

The existing code handles everything else:

- **Wrapping.** The limit makes `materialize` wrap the root in a page subquery.
- **Relations.** Relations, aggregates and filters keep working unchanged.
- **Nested levels.** Added to the relation pipeline, the same pass paginates nested relations through a lateral join or a ranked CTE, depending on the database.

The example is illustrative: `QueryRequest` has no `after` cursor today, and adding one is the other change this feature needs.

### Testing a pass alone

A pipeline of one pass plans only that capability:

```python
plan = Pipeline((Filtering(),)).plan(level)
assert plan.rows.where == ...
```

The tests in `tests/unit/transpiler/passes/` plan whole queries with `plan_sql`, which returns the SQL lines and fails when the statement reads the same data twice.

### Where to put new code

| To... | Edit |
|---|---|
| support a new query argument or field kind | a new pass in `_passes/`, wired in `_passes/__init__.py` |
| read a column or add a join from a pass | a `Level` service in `_core/level.py` |
| change how a relation joins its parent | `_core/attach.py` |
| change when a level becomes a subquery | `_core/materialize.py` |
| change the SQL clauses or their order | `_core/render.py` |
| change how rows become objects | `_executor.py` |

## Optimizations

The transpiler holds a second rule: **a statement never reads or computes the same data twice**, unless two parts of the query need different data from the same table. Most of the optimizations below fall out of the data structures rather than special cases.

### One aggregate join for filter, order and selection

Joins are keyed by node, and an aggregate join carries every function the request needs on its node. A query that orders by a sum and selects a count reads `fruit` once:

```graphql
{
    colorsPaginated(limit: 2, orderBy: { fruitsAggregate: { sum: { sweetness: ASC } } }) {
        name
        fruitsAggregate { count }
    }
}
```

```sql
SELECT color.name, color.id, color.count_1
  FROM (
        SELECT color.name, color.id, anon_1.sum_1, anon_1.count_1
          FROM color
          JOIN LATERAL (
                SELECT sum(fruit_1.sweetness) AS sum_1, count(*) AS count_1
                  FROM fruit AS fruit_1
                 WHERE color.id = fruit_1.color_id
               ) AS anon_1 ON TRUE
         ORDER BY anon_1.sum_1 ASC
         LIMIT 2
       ) AS color
 ORDER BY color.sum_1 ASC
```

The ordering needs the aggregate inside the page subquery. The selection asks for the same join key, gets the existing join, and `materialize` exports its count through the subquery rather than computing it again outside.

### Wrapping exports rather than joining again

When `materialize` wraps a level, it exports through the subquery every join the rows stage already made, such as an aggregate or a to-one relation used by a filter or an ordering, and rewrites the projection to read the exported columns. `groupsPaginated(limit: 2, orderBy: { color: { name: ASC } }) { name color { name } }` joins `color` once, inside the page, and the selected `color` reads it from there.

### To-one filters become inner joins

A filter through a to-one relation drops the rows whose relation does not match, so the join serving the filter can be an inner join, and the selection reuses it:

```graphql
{ groups(filter: { color: { name: { eq: "red" } } }) { name color { name } } }
```

```sql
SELECT "group".name, "group".id, color_1.name, color_1.id
  FROM "group"
  JOIN color AS color_1 ON color_1.id = "group".color_id
 WHERE color_1.name = 'red'
```

### EXISTS without a copy of the root

An `EXISTS` starts from the filtered relation and correlates to the outer row; it never reads a second copy of the root table. When only some branches of an `OR` need a relation, the filter splits at the subquery boundary: `EXISTS(A OR B)` becomes `EXISTS(A) OR B` when `B` reads only the root, so a color without fruits can still pass `B`.

### Identical CTEs are shared

A CTE has no correlation to a parent row, so two parts of a query on SQLite or MySQL can produce the same CTE body — the same aggregate reached by two paths, for instance. `share_ctes` compares the compiled bodies and keeps one CTE for all of them. Two ranked CTEs that differ only in their rank windows also merge into one CTE carrying every rank.

### Aliases of one relation share one read

GraphQL aliases let a client ask for one relation twice with different arguments:

```graphql
{
    colors {
        name
        sweetFirst: fruits(orderBy: { sweetness: DESC }) { name }
        sourFirst: fruits(orderBy: { sweetness: ASC }) { name }
    }
}
```

Read separately, each alias is a join of its own, and two to-many joins multiply rows: a color with 5 fruits returns 5 × 5 = 25 rows. Instead, `Relations` groups the aliases of one relationship, and `Level.plan_siblings` plans one read with one rank per alias (simplified):

```sql
SELECT color.name, color.id, anon_1.name, anon_1.id, anon_1.rank_1, anon_1.rank_2
  FROM color
  LEFT OUTER JOIN LATERAL (
        SELECT fruit_1.name, fruit_1.id,
               row_number() OVER (ORDER BY fruit_1.sweetness DESC, fruit_1.id) AS rank_1,
               row_number() OVER (ORDER BY fruit_1.sweetness ASC,  fruit_1.id) AS rank_2
          FROM fruit AS fruit_1
         WHERE color.id = fruit_1.color_id
       ) AS anon_1 ON TRUE
```

The color with 5 fruits now returns 5 rows. The executor fills `sweetFirst` in `rank_1` order and `sourFirst` in `rank_2` order. With pagination, each alias keeps only the ranks of its page, and the read keeps the rows at least one alias needs (`rank_1 <= 2 OR rank_2 <= 2`). SQLite and MySQL apply the same idea with one ranked CTE.

The rule has one measured exception. On PostgreSQL, when every alias has a small page — the product of their `offset + limit` is at most 16 — two index-backed top-N lateral joins outrun one ranked read of every fruit, so the aliases stay separate.

### A checker enforces the rule

`tests/duplicate_reads.py` compiles every statement the integration and pass tests produce, and fails when a table, lateral join, CTE or aggregate is read twice with the same correlation. The few cases where two reads need different data are allowed duplicates, each with a test:

- a hooked to-one relation that is both filtered and selected;
- an `EXISTS` filter next to the selection of the same to-many relation;
- a user statement or custom filter subquery the transpiler cannot merge;
- the DML subqueries some databases require;
- the small-page sibling lateral joins above.

A test that needs another duplicate must give its reason with the `allow_duplicate_reads(reason=...)` marker.

## Module map

All paths are relative to `src/strawchemy/transpiler/`.

| Module | Responsibility |
|---|---|
| `_transpiler.py` | `Transpiler`: builds the request and the root level, runs a pipeline |
| `_core/request.py` | `QueryRequest`: the client's input at one level |
| `_core/split.py` | divides a filter into direct predicates and `EXISTS` branches |
| `_core/level.py` | `Level` and its services, `PlanContext` |
| `_core/rowset.py` | `RowSet`, `Projection`, `Join`, `AggregateJoin`, order priorities |
| `_core/pipeline.py` | `Pass`, `PassBase`, `Pipeline`, `Pipelines` |
| `_core/materialize.py` | inline or wrap; moving a projection onto a subquery |
| `_core/attach.py` | lateral and CTE joins for relations and aggregates |
| `_core/render.py` | the only SQL builder: `render_rows`, `render_plan`, `order_terms` |
| `_core/rewrite.py`, `_core/share.py` | plan rewrites: rebasing onto a subquery, sharing CTEs |
| `_core/plan.py` | `QueryPlan`, the immutable result of planning a level |
| `_passes/` | one module per pass, and `DEFAULT_PIPELINES` |
| `_executor.py` | runs the statement and rebuilds objects from rows |
