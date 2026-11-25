"""
Compiled validation masks of endpoints of the request being sent (`BoundEndpoint.set_validation_mask`).

An endpoint with a validation mask makes the mask, compiled by its API, available to validators of responses
(callbacks of requests) while its request is sent - they validate only the fields given by the mask. Masks are given
by JSON-RPC methods of the endpoints (`block_api.get_block`), a batch gives masks of all its calls.
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from types import MappingProxyType
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from collections.abc import Generator, Mapping

__all__ = [
    "compiled_validation_mask_of",
    "compiled_validation_masks",
    "current_compiled_validation_masks",
]

_COMPILED_MASKS: Final[ContextVar[Mapping[str, object]]] = ContextVar("_COMPILED_MASKS", default=MappingProxyType({}))


def compiled_validation_mask_of(jsonrpc_method: str) -> object | None:
    """
    Compiled validation mask of the endpoint of the request being sent - for validators of responses.

    What the compiled mask is depends on the API (`AbstractApi._compile_validation_mask`), e.g. a validation model
    reduced to the fields of the mask.

    Args:
        jsonrpc_method: The JSON-RPC method of the endpoint, e.g. `block_api.get_block`.

    Returns:
        The compiled mask, `None` when the endpoint has no mask (all fields are validated).
    """
    return _COMPILED_MASKS.get().get(jsonrpc_method)


def current_compiled_validation_masks() -> Mapping[str, object]:
    """Compiled masks of the request being sent - by JSON-RPC methods (kept by calls of batches until they are sent)."""
    return _COMPILED_MASKS.get()


@contextmanager
def compiled_validation_masks(masks: Mapping[str, object]) -> Generator[None]:
    """Make the compiled masks (by JSON-RPC methods) available to validators of the request sent in the context."""
    if not masks:
        yield
        return
    token = _COMPILED_MASKS.set(MappingProxyType({**_COMPILED_MASKS.get(), **masks}))
    try:
        yield
    finally:
        _COMPILED_MASKS.reset(token)
