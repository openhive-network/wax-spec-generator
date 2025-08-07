from __future__ import annotations

from msgspec import Struct

from api_client_generator._private.common.models_aliased import AnyJson


class RestApiMethod(Struct):
    tags: list[str]
    summary: str
    description: str
    operationId: str  # NOQA: N815
    responses: AnyJson
    parameters: list[AnyJson] | None = None
