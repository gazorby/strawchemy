from __future__ import annotations

import re
from typing import Annotated

from pydantic import AfterValidator


def _valid_regex(string: str) -> str:
    try:
        re.compile(string)
    except re.error as error:
        msg = f"Invalid regular expression: '{string}'"
        raise ValueError(msg) from error
    else:
        return string


RegexPatternStr = Annotated[str, AfterValidator(_valid_regex)]
