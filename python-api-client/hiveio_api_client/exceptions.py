"""
Exceptions raised by handles of the package (`SyncRemoteHandle`, `AsyncRemoteHandle` and their batches).

- `CommunicationError` - no response was received (connection failed, `TimeoutExceededError`); such requests are retried
  as set by `RemoteHandleSettings`,
- `ResponseError` - a response was received, but it is an error: `HttpStatusError`, `JsonRpcResponseError` or
  `InvalidResponseError`; not retried.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Self

if TYPE_CHECKING:
    from collections.abc import Mapping

    from hiveio_api_client._communication.abc.communicator_models import Response
    from hiveio_api_client._communication.url import HttpUrl

__all__ = [
    "CommunicationError",
    "HiveioApiClientError",
    "HttpStatusError",
    "InvalidResponseError",
    "JsonRpcResponseError",
    "ResponseError",
    "ResponseNotReadyError",
    "TimeoutExceededError",
    "UnsupportedBatchCallError",
]


class HiveioApiClientError(Exception):
    """Base class of all exceptions defined in the package."""


class CommunicationError(HiveioApiClientError):
    """The request was not answered - connecting to the service or sending the request failed."""

    def __init__(self, url: HttpUrl, request: str | None, reason: str) -> None:
        super().__init__(f"Request to `{url}` failed: {reason}")
        self.url = url
        self.request = request
        """Body of the request."""


class TimeoutExceededError(CommunicationError):
    """The service did not answer within the timeout of the request."""

    def __init__(self, url: HttpUrl, request: str | None, timeout_secs: float | None) -> None:
        super().__init__(url, request, f"no response within {timeout_secs} seconds")
        self.timeout_secs = timeout_secs


class ResponseError(HiveioApiClientError):
    """The service answered with an error - see subclasses."""

    def __init__(self, message: str, response: Response) -> None:
        super().__init__(message)
        self.response = response
        """The received response (the whole one for errors of calls of a batch)."""


class HttpStatusError(ResponseError):
    """The response has an HTTP error status (4xx, 5xx) and no JSON-RPC error."""

    def __init__(self, response: Response) -> None:
        super().__init__(f"Service responded with HTTP status {response.status_code}: {response.body}", response)
        self.status_code = response.status_code


class JsonRpcResponseError(ResponseError):
    """The JSON-RPC response has an `error` instead of the `result` of the call."""

    def __init__(self, response: Response, error: dict[str, object], request_id: object) -> None:
        super().__init__(f"Service responded with JSON-RPC error: {error}", response)
        self.error = error
        """The `error` object of the JSON-RPC response, as received."""
        self.request_id = request_id
        """`id` of the JSON-RPC response - identifies the call of a batch."""

    @classmethod
    def of_payload(cls, response: Response, payload: Mapping[str, object]) -> Self:
        """Error of a parsed JSON-RPC response without `result` - its `error` (not an object - as `message` of one)."""
        error = payload.get("error", {})
        return cls(response, error if isinstance(error, dict) else {"message": error}, payload.get("id"))


class InvalidResponseError(ResponseError):
    """The response is not JSON, does not answer the request or its result does not match the expected type."""


class ResponseNotReadyError(HiveioApiClientError):
    """The result of a call of a batch was accessed before the batch was sent."""


class UnsupportedBatchCallError(HiveioApiClientError):
    """Only JSON-RPC calls can be sent in a batch - not calls of REST endpoints."""
