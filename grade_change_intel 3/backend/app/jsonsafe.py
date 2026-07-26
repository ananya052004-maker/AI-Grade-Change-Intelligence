"""
jsonsafe.py
Starlette's JSONResponse uses allow_nan=False (strict RFC 8259 JSON), so any
NaN/Infinity anywhere in a response body -- e.g. a sheet-break gap in a BW
history array, or a censored transition's stabilization_time_sec -- 500s the
whole request. NaN is genuinely meaningless in strict JSON; the fix is to
convert it to `null` at the boundary, not to loosen the encoder.
"""

from __future__ import annotations

import math
from typing import Any

from starlette.responses import JSONResponse


def sanitize(obj: Any) -> Any:
    if isinstance(obj, float):
        return None if (math.isnan(obj) or math.isinf(obj)) else obj
    if isinstance(obj, dict):
        return {k: sanitize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [sanitize(v) for v in obj]
    return obj


class SanitizingJSONResponse(JSONResponse):
    def render(self, content: Any) -> bytes:
        return super().render(sanitize(content))
