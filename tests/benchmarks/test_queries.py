from __future__ import annotations

import pytest

from tests.integration.typing import RawRecordData
from tests.typing import AnyQueryExecutor
from tests.utils import maybe_async


@pytest.mark.benchmark(group="queries")
async def test_single(any_query: AnyQueryExecutor, raw_users: RawRecordData) -> None:
    await maybe_async(
        any_query(
            """
            query GetUser($id: Int!) {
                user(id: $id) {
                    name
            }
            }
            """,
            {"id": raw_users[0]["id"]},
        )
    )
