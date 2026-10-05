# The transpiler

The transpiler turns one GraphQL query into one SQL statement, runs it, and turns the rows back into the objects the
GraphQL response needs. It lives in `src/strawchemy/transpiler/`.

This guide assumes you know Python, SQLAlchemy and GraphQL, but not how a transpiler works. It starts with the problem
the transpiler solves, then the architecture, then the details: how a query becomes SQL, how to add a feature, and which
optimizations the design makes possible.

The examples run on a small schema: a `color` has many `fruit`, and a `group` has one `color`. Their SQL is the
planner's output for PostgreSQL unless stated otherwise, trimmed of the clauses that do not matter to the point.

## The problem: trees in, tables out

A GraphQL query is a tree. Each field can select fields of its own, and the response has the same shape:

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

A SQL query returns a flat table. To read colors and their fruits in one statement, the transpiler joins the two tables,
and each color appears once per fruit:

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

Strawchemy keeps one rule: **one GraphQL request produces one SQL statement.** The database does all the reading in one
round trip, and the transpiler rebuilds the tree from the flat rows afterwards.

The join is easy. The hard part is that every argument in the query means something *per node of the tree*, while SQL
applies clauses to the whole flat table:

- `colors(limit: 2)` means two colors. A `LIMIT 2` on the table above returns two *rows*, which is red twice.
- `fruits(orderBy: { sweetness: DESC }, limit: 2)` means the two sweetest fruits *of each color*, not of the whole table.
- `colors(filter: { fruits: { sweetness: { gt: 5 } } })` means colors with at least one sweet fruit. Filtering the
  joined rows would also hide the color's other fruits from the selection.
- `fruitsAggregate { count }` needs one value per color, which a GROUP BY on the main query would collapse rows for.

So the transpiler must decide, for every part of the tree, where in one SQL statement it belongs: in the main FROM, in a
subquery, in a LATERAL join, in a CTE or in an EXISTS. The rest of this guide explains how it decides.

## Architecture

### The journey of a query

```
GraphQL selection ──► QueryNode tree ──► Level + QueryRequest ──► Pipeline ──► QueryPlan ──► SELECT
   (strawberry)        (repository)          (_core)              (_passes)     (_core)      (render)
                                                                                                │
GraphQL response ◄── strawberry types ◄── QueryResult ◄────────── executor ◄────── rows ◄──────┘
```

1. The repository reads the strawberry selection into a **`QueryNode` tree**. Each node is a field: a column, a relation,
   an aggregate or a computed value. A relation node carries its arguments (filter, ordering, pagination).
2. `Transpiler.select_executor` wraps the tree and the root arguments in a **`QueryRequest`**, creates the root
   **`Level`**, and runs the root **`Pipeline`** on it.
3. The pipeline's **passes** fill in two frozen data structures, a **`RowSet`** and a **`Projection`**, and the level
   turns them into a **`QueryPlan`**.
4. `render_plan` builds the SQLAlchemy `Select` from the plan. It is the only code that builds the final statement.
5. The **executor** runs it and regroups the flat rows into objects, one collection per relation node and parent.

### Levels: cutting the tree into SQL scopes

A **level** is one SQL scope: a FROM clause with its own WHERE, ORDER BY and LIMIT. The root of the query is always a
level. Below it, the transpiler cuts the tree wherever a node needs rows chosen independently of its parent:

```
colors(limit: 2)                          ── root level (paged: wrapped in a subquery)
├── name
├── fruits { name }                       ── relation, no arguments: folded into the root as a plain join
├── sweetest: fruits(orderBy, limit: 2)   ── relation level of its own: LATERAL join or ranked CTE
└── fruitsAggregate { count }             ── aggregate join: grouped LATERAL or grouped CTE
filter: { fruits: { sweetness: gt 5 } }   ── EXISTS level, correlated to the root
```

There are four kinds of level, each planned by its own pipeline:

| Kind | Stands for | Becomes |
|---|---|---|
| `root` | the field the client queried | the main statement, or a page subquery when it is paginated |
| `relation` | a selected relation | a plain join, a LATERAL join or a ranked CTE |
| `exists` | a filter on a to-many relation | an `EXISTS (...)` predicate in the parent's WHERE |
| `dml` | the filter of an UPDATE or DELETE | WHERE predicates on the table |

A level never builds SQL itself. It offers **services** that read columns and add joins: `column`, `path_column`,
`aggregate`, `plan_child`, `plan_exists` and `materialize`, among others. A level also knows its parent, so a child level
can reuse what its ancestors already joined.

### Two stages: which rows, then what to read

Every level answers two questions, in order:

1. **Rows stage: which rows?** Filter, ordering, DISTINCT ON, limit and offset, query hooks that restrict rows.
2. **Projection stage: what is read from those rows?** Columns, relations, aggregates, JSON extractions.

Each stage builds one frozen value:

- **`RowSet`** holds the source alias, its joins, WHERE predicates, ORDER BY terms, DISTINCT ON, limit, offset, and the
  query hooks' statement edits.
- **`Projection`** holds the entities to load, the columns to select, the joins of the projection, and the maps the
  executor reads results with.

Neither builds SQL. Both are immutable: every change returns a new value, so a function can never alter what another
one already planned.

The split matters because the two stages need different things from SQL. Take `colors(limit: 2) { fruits { name } }`.
The `LIMIT` belongs to the rows stage and must count colors; the fruit join belongs to the projection stage and must
not be counted. Keeping them in separate values lets the level decide afterwards how to combine them.

### Passes and pipelines

Each feature of the query language is a **pass**: one class with one method per stage.

```python
class Pass(Protocol):
    def rows(self, level: Level, rows: RowSet) -> RowSet: ...
    def project(self, level: Level, rows: RowSet, projection: Projection) -> Projection: ...
```

A pass reads its part of `level.request` and returns a new `RowSet` or `Projection`. `Filtering` adds WHERE predicates,
`Ordering` adds ORDER BY terms, `OffsetPagination` sets the limit and offset, `Relations` plans the selected relations,
and so on. A pass that acts on one stage only subclasses `PassBase`, which returns the other stage's input unchanged.

A **pipeline** is an ordered tuple of passes and one loop:

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

Every rows stage runs before any projection stage, so a projection sees the finished `RowSet` and can reuse its joins.
The four pipelines are assembled in one place, `_passes/__init__.py`:

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

The order of the passes carries no meaning. ORDER BY terms carry a priority (`HOOK`, `CLIENT`, then `DETERMINISTIC`),
and the renderer sorts them, so `Ordering` and `QueryHooks` can run in either order and produce the same SQL.

| Pass | Stage | What it does |
|---|---|---|
| `UserStatement` | rows | restricts the root to a statement the user gave the field (`filter_statement`) |
| `QueryHooks` | both | applies query hooks: statement edits on the rows, column and relationship loads on the projection |
| `Filtering` | rows | turns the filter into WHERE predicates, joins and EXISTS subqueries |
| `Ordering` | rows | client ordering, else the default ordering, then primary keys for a stable order |
| `DistinctOn` | rows | sets DISTINCT ON |
| `OffsetPagination` | rows | sets limit and offset |
| `Selection` | project | loads the selected columns and JSON extractions |
| `Relations` | project | plans each selected relation as a child level and joins it |
| `Aggregations` | project | selects the aggregates of relations (`fruitsAggregate { count }`) |
| `RootAggregations` | project | window functions for aggregates over the whole result |

### materialize: inline or wrap

After both stages, `Level.materialize` makes the one structural decision of the transpiler: can the rows stage share
the FROM clause of the projection, or must it become a subquery?

The rows stage stays **inline** when it only filters and orders. Its WHERE and ORDER BY go into the main statement,
next to the projection's joins:

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

With a limit, inlining would count color × fruit rows. `materialize` **wraps** the rows stage in a subquery, then moves
the projection onto it:

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

No pass asked for the subquery. `OffsetPagination` only set `limit = 2`; `materialize` saw a limit and wrapped. The
subquery exports exactly the columns the projection reads (`name` for the selection, `id` for the fruit join), because
`materialize` walks the projection and collects them. Nobody maintains a list of columns to export by hand.

For a relation level, the same decision picks between a plain join and a LATERAL join or ranked CTE, covered next.

## From a tree to one statement

### Relations that only follow the tree

A relation without arguments needs no rows of its own: it reads every related row. `Relations` asks
`level.plan_child(node, ...)`, which plans the relation on the relation pipeline. Its rows stage stays empty, so
`materialize` folds it into the parent as a `LEFT OUTER JOIN`, and the child's projection merges into the parent's. The
tree flattens into joins: `groups { color { fruits { name } } }` is two joins in one FROM.

### Relations with their own rows: LATERAL or ranked CTE

`fruits(orderBy: { sweetness: DESC }, limit: 2)` needs the two sweetest fruits of *each* color. The relation level's
rows stage now holds an ORDER BY and a limit, so `materialize` hands it to `attach_rows`, which has two strategies.

On databases with LATERAL (PostgreSQL), the child is a subquery evaluated once per parent row, correlated on the
relationship:

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

On databases without LATERAL (SQLite, MySQL), the child is a CTE that ranks every fruit within its color, and the join
keeps the ranks of the page:

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

Both shapes give the same rows. `attach.py` is the only module that knows about LATERAL and CTE; it reads
`DatabaseFeatures.supports_lateral` and nothing else needs to.

### Filters on to-many relations: EXISTS

`colors(filter: { fruits: { sweetness: { gt: 5 } } }) { name fruits { name } }` asks for colors that have a sweet fruit,
with *all* their fruits. Filtering the fruit join would drop the sour ones from the selection, and joining a second time
in the main FROM would repeat each color once per sweet fruit. The filter goes into its own `exists` level instead,
correlated to the parent:

```sql
SELECT color.name, color.id, fruit_1.name, fruit_1.id
  FROM color
  LEFT OUTER JOIN fruit AS fruit_1 ON color.id = fruit_1.color_id   -- selection: all fruits
 WHERE EXISTS (
        SELECT 1 FROM fruit AS fruit_2                              -- filter: any sweet fruit
         WHERE color.id = fruit_2.color_id AND fruit_2.sweetness > 5
       )
```

`split.py` decides, once per filter, which parts the rows stage tests directly and which go to an EXISTS. A filter on a
to-one relation needs no EXISTS: it cannot multiply rows, so it joins directly (see
[To-one filters become inner joins](#to-one-filters-become-inner-joins)).

### Aggregates: one value per parent

`fruitsAggregate { count }` needs one count per color. A GROUP BY on the main statement would collapse the joined
rows, so the aggregate is a join of its own, computed by `attach_grouped`: a LATERAL of aggregate functions on
PostgreSQL, a CTE grouped by the foreign key elsewhere. It returns one row per parent, so it never multiplies rows.

### Rebuilding the tree

The executor receives flat rows and rebuilds the tree:

- The SELECT lists the root entity first, then one entity per relation, so each row holds a color, a fruit, and so on.
- SQLAlchemy's identity map returns the same Python object for the same primary key, so red appears once even though
  it spans two rows.
- For each relation node, the executor collects the related objects **per parent object**, so `fruits` of red and
  `fruits` of green stay apart.
- Computed values (aggregates, JSON extractions) are read from labelled columns and stored under the node that asked
  for them.

The repository then walks the `QueryNode` tree once more and builds the strawberry objects from these collections.

## Adding a feature

### What a new feature touches

A new capability is usually one new pass and one line in `DEFAULT_PIPELINES`. Four properties of the design keep the
rest of the code untouched:

1. **Passes do not know each other.** A pass imports `_core` and never another pass; `_core` imports no pass. A test
   (`tests/unit/transpiler/test_architecture.py`) enforces this. Passes interact only through level services and the
   data they return.
2. **Order does not matter.** ORDER BY terms carry priorities, and joins are stored under keys, so a pass never needs to
   run before or after another.
3. **Joins are keyed, not counted.** A join is stored under `(kind, node)`. Asking for a join that already exists
   returns the existing one. A new pass that reads an aggregate another pass already joined gets the same join for free,
   without coordinating with it.
4. **Structure follows data.** A pass describes *what* it needs (a limit, an ORDER BY term, a WHERE predicate);
   `materialize` and `attach` decide *how* to lay it out in SQL. A new pass that sets a limit gets the subquery, the
   LATERAL join or the ranked CTE without asking for any of them.

### Example: cursor pagination

Suppose you want Relay-style cursor pagination: "the 10 colors after the color named `blue`, ordered by name". The
pass sets data on the `RowSet` and nothing else:

```python
class CursorPagination(PassBase):
    def rows(self, level: Level, rows: RowSet) -> RowSet:
        request = level.request
        rows = replace(rows, limit=request.limit)
        if request.after is None:
            return rows
        # A level service: the column of the cursor's node, read from this level's alias.
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

The pass does not handle any of the following, because the existing code already does:

- **Wrapping.** The limit makes `materialize` wrap the root in a page subquery.
- **Relations.** Relations, aggregates and filters keep working, unchanged.
- **Nested levels.** Added to the relation pipeline too, the same pass paginates nested relations, through a LATERAL
  join or a ranked CTE depending on the database.

The example is illustrative: `QueryRequest` has no `after` cursor today, and adding one is the other change this
feature needs.

### Testing a pass alone

A pipeline of one pass plans only that capability, which makes a focused test easy:

```python
plan = Pipeline((Filtering(),)).plan(level)
assert plan.rows.where == ...
```

The tests in `tests/unit/transpiler/passes/` plan whole queries with `plan_sql`, which returns the SQL lines and fails
when the statement reads the same data twice (see below).

### Where to put new code

| You want to... | Put it in |
|---|---|
| support a new query argument or field kind | a new pass in `_passes/`, wired in `_passes/__init__.py` |
| read a column or add a join from a pass | a `Level` service (`_core/level.py`) |
| change how a relation joins its parent | `_core/attach.py` |
| change when a level becomes a subquery | `_core/materialize.py` |
| change the SQL clauses or their order | `_core/render.py` |
| change how rows become objects | `_executor.py` |

## Optimizations

The transpiler holds one more rule: **a statement never reads or computes the same data twice**, except where two parts
of the query need different data from the same table. The design makes most of the optimizations below fall out of the
data structures rather than special cases.

### One aggregate join for filter, order and selection

Joins are keyed by node, and an aggregate join is built once with every function the request needs on its node. A query
that orders by a sum and selects a count reads `fruit` once:

```graphql
{ colorsPaginated(limit: 2, orderBy: { fruitsAggregate: { sum: { sweetness: ASC } } }) {
    name
    fruitsAggregate { count }
} }
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

The ordering needed the aggregate inside the page subquery. The selection asked for the same join key, got the existing
join, and `materialize` exported its count through the subquery instead of computing it again outside.

### Wrapping exports, it never joins again

When `materialize` wraps a level, every join the rows stage already made (an aggregate, a to-one relation used by a
filter or an ordering) is exported through the subquery, and the projection is rewritten to read the exported columns.
`groupsPaginated(limit: 2, orderBy: { color: { name: ASC } }) { name color { name } }` joins `color` once, inside the
page, and the selected `color` reads it from there.

### To-one filters become inner joins

A filter through a to-one relation drops the rows whose relation does not match, so the join that serves the filter
can be an INNER join, and the selection reuses it:

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

An EXISTS starts from the filtered relation and correlates to the outer row; it never reads a second copy of the root
table. When only some branches of an OR need a relation, the filter is split at the subquery boundary:
`EXISTS(A OR B)` becomes `EXISTS(A) OR B` when `B` reads only the root, so a color without fruits can still pass `B`.

### Identical CTEs are shared

On databases without LATERAL, a CTE is not correlated to a parent row, so two parts of a query can produce the same
CTE body, for example the same aggregate reached by two paths. `share_ctes` compares the compiled bodies and keeps one
CTE for all of them. Two ranked CTEs that differ only in their rank windows also become one CTE carrying every rank.

### Aliases of one relation share one read

GraphQL aliases let a client ask for the same relation twice with different arguments:

```graphql
{
  colors {
    name
    sweetFirst: fruits(orderBy: { sweetness: DESC }) { name }
    sourFirst: fruits(orderBy: { sweetness: ASC }) { name }
  }
}
```

Read separately, each alias is a join of its own, and two to-many joins multiply rows: a color with 5 fruits returns
5 × 5 = 25 rows. Instead, `Relations` groups the aliases of one relationship and `Level.plan_siblings` plans one read
with one rank per alias (simplified PostgreSQL):

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

The color with 5 fruits now returns 5 rows. The executor fills `sweetFirst` in `rank_1` order and `sourFirst` in
`rank_2` order. With pagination, each alias keeps only the ranks of its page, and the read keeps the rows that at least
one alias needs (`rank_1 <= 2 OR rank_2 <= 2`). SQLite and MySQL use the same idea with one ranked CTE.

The rule has a measured exception. On PostgreSQL, when every alias has a small page (the product of their
`offset + limit` is at most 16), two index-backed "top N" LATERALs are faster than one ranked read of every fruit, so
the aliases stay separate.

### A checker keeps the rule honest

`tests/duplicate_reads.py` compiles every statement the integration tests and the pass tests produce, and fails when a
table, LATERAL, CTE or aggregate is read twice with the same correlation. The few cases where two reads need different
data are listed as *allowed duplicates*, each with a test:

- a hooked to-one relation that is both filtered and selected;
- an EXISTS filter next to the selection of the same to-many relation;
- a user statement or custom filter subquery the transpiler cannot merge;
- the DML subqueries some databases require;
- the small-page sibling LATERALs above.

A test that needs another duplicate must say why, with the `allow_duplicate_reads(reason=...)` marker.

## Module map

| Module | Responsibility |
|---|---|
| `_transpiler.py` | `Transpiler`: builds the request and the root level, runs a pipeline |
| `_core/request.py` | `QueryRequest`: the client's input at one level |
| `_core/split.py` | divides a filter into direct predicates and EXISTS branches |
| `_core/level.py` | `Level` and its services, `PlanContext` |
| `_core/rowset.py` | `RowSet`, `Projection`, `Join`, `AggregateJoin`, order priorities |
| `_core/pipeline.py` | `Pass`, `PassBase`, `Pipeline`, `Pipelines` |
| `_core/materialize.py` | inline or wrap; moving a projection onto a subquery |
| `_core/attach.py` | LATERAL and CTE joins for relations and aggregates |
| `_core/render.py` | the only SQL builder: `render_rows`, `render_plan`, `order_terms` |
| `_core/rewrite.py`, `_core/share.py` | plan rewrites: rebasing onto a subquery, sharing CTEs |
| `_core/plan.py` | `QueryPlan`, the immutable result of planning a level |
| `_passes/` | one module per pass, and `DEFAULT_PIPELINES` |
| `_executor.py` | runs the statement and rebuilds objects from rows |
