from __future__ import annotations

import pytest

from tests.typing import AnyQueryExecutor
from tests.utils import maybe_async

from .typing import RawRecordData

pytestmark = [pytest.mark.integration]


async def test_field_extension(any_query: AnyQueryExecutor, raw_fruits: RawRecordData) -> None:
    result = await maybe_async(
        any_query(
            """
            query fruitWithExtension($id: Int!) {
                fruitWithExtension(id: $id) {
                    name
            }
            }
            """,
            {"id": raw_fruits[0]["id"]},
        )
    )

    assert not result.errors
    assert result.data
    assert result.data["fruitWithExtension"] == {"name": raw_fruits[0]["name"]}
