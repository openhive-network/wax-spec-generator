from __future__ import annotations

from msgspec import Struct, field

from api_client_generator._private.common.models_aliased import AnyJson


class RestApiMethod(Struct):
    tags: list[str]
    summary: str
    description: str
    operationId: str  # NOQA: N815
    responses: AnyJson
    parameters: list[AnyJson] | None = None
    x_response_headers: list[AnyJson] | None = field(name="x-response-headers", default=None)
