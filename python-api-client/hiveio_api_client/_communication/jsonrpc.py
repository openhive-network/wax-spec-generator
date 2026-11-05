"""
JSON-RPC envelope of API calls.

Results of responses are built by `value_builder` of the installed `ValueCodec` (see `hiveio_api_client._values`).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Generic, TypeVar

from hiveio_api_client._values import value_builder

if TYPE_CHECKING:
    from collections.abc import Mapping

__all__ = [
    "ExpectResultT",
    "JSONRPCError",
    "JSONRPCRequest",
    "JSONRPCResult",
    "build_response",
    "jsonrpc_id",
]

ExpectResultT = TypeVar("ExpectResultT")

JsonRpcIdT = int | str | None


def jsonrpc_id(value: object) -> JsonRpcIdT:
    """The id of a JSON-RPC call or response - `None` when it is not a number nor a string."""
    return value if isinstance(value, int | str) else None


@dataclass(frozen=True, kw_only=True)
class JSONRPCRequest:
    """A JSON-RPC call - the method (e.g. `database_api.find_accounts`) with its parameters."""

    method: str
    params: object = field(default_factory=dict)
    id_: JsonRpcIdT = 0
    jsonrpc: str = "2.0"

    def json(self) -> str:
        """The call as a JSON-RPC request body - the parameters have to be JSON builtins."""
        return json.dumps({"id": self.id_, "jsonrpc": self.jsonrpc, "method": self.method, "params": self.params})


@dataclass(frozen=True, slots=True)
class JSONRPCResult(Generic[ExpectResultT]):
    """A JSON-RPC response with the result of the call (built without validation, see `build_response`)."""

    result: ExpectResultT
    id_: JsonRpcIdT = 0
    jsonrpc: str = "2.0"


@dataclass(frozen=True, slots=True)
class JSONRPCError:
    """A JSON-RPC response with an error instead of the result - the `error` object as it was received."""

    error: dict[str, object]
    id_: JsonRpcIdT = 0
    jsonrpc: str = "2.0"


def build_response(
    expected_type: type[ExpectResultT], response: Mapping[str, object]
) -> JSONRPCResult[ExpectResultT] | JSONRPCError:
    """
    Build the response of an API call from parsed JSON-RPC response.

    Args:
        expected_type: Expected type of the result - built by `value_builder` of the installed `ValueCodec`.
        response: Parsed JSON-RPC response (e.g. result of `json.loads`).

    Returns:
        The response with the result built as `expected_type`, or `JSONRPCError` when there is no result. Members of
        the envelope of other types than in JSON-RPC are replaced: `id` by `None`, `jsonrpc` by its text and `error`
        (not an object) by `{"message": <the error>}`.

    Raises:
        ValueError: When the result does not match `expected_type` (raised by the value builder of the codec).
    """
    build_result = value_builder(expected_type)
    id_ = jsonrpc_id(response.get("id"))
    jsonrpc = str(response.get("jsonrpc", "2.0"))
    if "result" not in response:
        error = response.get("error", {})
        return JSONRPCError(error=error if isinstance(error, dict) else {"message": error}, id_=id_, jsonrpc=jsonrpc)
    return JSONRPCResult(result=build_result(response["result"]), id_=id_, jsonrpc=jsonrpc)
