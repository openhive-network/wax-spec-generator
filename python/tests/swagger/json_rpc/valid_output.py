from __future__ import annotations

from typing import Any


def get_valid_params_for_second_endpoint() -> dict[str, type[str] | type[int] | type[list[Any]]]:
    """Get valid params for the second endpoint generated from the swagger."""
    from .api_description import SecondEndpointResponseItem  # type: ignore[import-untyped]

    return {
        "return": list[SecondEndpointResponseItem],
        "some_string": str,
        "some_integer": int,
        "some_another_string": str,
    }


def get_valid_params_for_first_endpoint() -> dict[str, Any]:
    """Get valid params for the first endpoint generated from the swagger."""
    from .api_description import FirstEndpointResponse  # type: ignore[import-untyped]

    return {
        "return": FirstEndpointResponse,
        "some_string": str,
        "some_integer": int,
        "some_another_string": str,
    }
