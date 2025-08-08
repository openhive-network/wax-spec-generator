from __future__ import annotations

from typing import Any

from msgspec import Struct, field


class RestApiMethod(Struct):
    tags: list[str]
    summary: str
    description: str
    operationId: str  # NOQA: N815
    responses: Any
    parameters: Any | None = None
    x_response_headers: Any | None = field(name="x-response-headers", default=None)
