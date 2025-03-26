"""GraphQL Constants.

This module defines constant keys used in GraphQL queries and mutations.

Constants:
    LIMIT_KEY: Key for the limit argument.
    OFFSET_KEY: Key for the offset argument.
    ORDER_BY_KEY: Key for the order_by argument.
    FILTER_KEY: Key for the filter argument.
    DISTINCT_ON_KEY: Key for the distinct_on argument.
    AGGREGATIONS_KEY: Key for the aggregations argument.
    NODES_KEY: Key for the nodes argument.
"""

from __future__ import annotations

LIMIT_KEY = "limit"
OFFSET_KEY = "offset"
ORDER_BY_KEY = "order_by"
FILTER_KEY = "filter"
DISTINCT_ON_KEY = "distinct_on"

AGGREGATIONS_KEY = "aggregations"
NODES_KEY = "nodes"

DATA_KEY = "data"
