from __future__ import annotations

import asyncio
import inspect
import json
import re
import time
from typing import TYPE_CHECKING, Final, Generic, TypeVar, cast

from hiveio_api_client._apis.abc.api import AbstractAsyncApi, AbstractSyncApi
from hiveio_api_client._apis.abc.api_collection import AbstractAsyncApiCollection, AbstractSyncApiCollection
from hiveio_api_client._apis.abc.sendable import AsyncSendable, SyncSendable
from hiveio_api_client._communication.abc.communicator_models import (
    AsyncCallbacks,
    Callbacks,
    Request,
    RequestContext,
    RequestTimings,
)
from hiveio_api_client._communication.http_transport import send_http_request
from hiveio_api_client._communication.jsonrpc import JSONRPCError, JSONRPCResult, build_response
from hiveio_api_client._communication.url import HttpUrl
from hiveio_api_client._remote_handle.batch_handle import AsyncBatchHandle, SyncBatchHandle
from hiveio_api_client.exceptions import (
    CommunicationError,
    HttpStatusError,
    InvalidResponseError,
    JsonRpcResponseError,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from hiveio_api_client._communication.abc.communicator_models import Methods, Response
    from hiveio_api_client._communication.jsonrpc import ExpectResultT
    from hiveio_api_client._remote_handle.settings import RemoteHandleSettings

ApiT = TypeVar("ApiT")
T = TypeVar("T")

_JSONRPC_MEMBER: Final[re.Pattern[str]] = re.compile(r'"jsonrpc"\s*:')
_HTTP_ERROR_STATUS: Final[int] = 400


class _RemoteHandle:
    """Sending requests to the service of the settings - common to synchronous and asynchronous handles."""

    def __init__(self, settings: RemoteHandleSettings) -> None:
        self.__settings = settings

    @property
    def settings(self) -> RemoteHandleSettings:
        return self.__settings

    def is_testnet(self) -> bool:
        """Whether the service is a testnet - override for handles of testnets."""
        return False

    def _merge_url(self, url: HttpUrl | None) -> HttpUrl:
        """URL of a request - the endpoint of the settings with the path and query of the given URL (of REST calls)."""
        endpoint = self.settings.http_endpoint
        return HttpUrl.factory(
            address=endpoint.address,
            port=endpoint.port,
            path=(url or endpoint).path,
            query=(url or endpoint).query,
            protocol=endpoint.protocol,
        )

    def _prepare_request(self, url: HttpUrl, method: Methods, data: str | None) -> Request:
        return Request(
            url=url,
            method=method,
            headers={"Content-Type": "application/json", "accept": "application/json"},
            body=data,
            timeout=self.settings.timeout,
        )

    def _retries_left(self, error: CommunicationError, retries_left: int) -> int:
        """Retries left after the next one - raises the error when no retry is left."""
        if retries_left == 0:
            raise error
        return retries_left - 1


def _check_response(context: RequestContext) -> None:
    """
    Reject responses with errors - the first callback of responses of requests of handles.

    Error callbacks of the request are called for the raised exceptions, as for exceptions of other callbacks. Errors
    of calls of a batch are checked by the batch - its response is an array.
    """
    response = cast("Response", context.response)  # callbacks of responses get the received response
    is_error_status = response.status_code >= _HTTP_ERROR_STATUS
    try:
        payload = response.json
    except json.JSONDecodeError as error:
        if is_error_status:
            raise HttpStatusError(response) from error
        raise InvalidResponseError(f"Response is not JSON: {response.body}", response) from error
    if _is_jsonrpc(context.request.body) and isinstance(payload, dict) and "result" not in payload:
        raise JsonRpcResponseError.of_payload(response, payload)
    if is_error_status:
        raise HttpStatusError(response)


def _is_jsonrpc(data: str | None) -> bool:
    """Whether the request is a JSON-RPC call - its body has the `jsonrpc` member (whitespace is allowed)."""
    return data is not None and _JSONRPC_MEMBER.search(data) is not None


def _built_result(response: Response, expected_type: type[ExpectResultT], *, is_jsonrpc: bool) -> ExpectResultT:
    """Result of an accepted response (see `_check_response`) - REST responses are the result as a whole."""
    payload = response.json
    envelope = payload if is_jsonrpc else {"result": payload}
    if not isinstance(envelope, dict):
        raise InvalidResponseError(f"Response is not a JSON-RPC object: {response.body}", response)
    try:
        built = build_response(expected_type, envelope)
    except ValueError as error:
        raise InvalidResponseError(f"Result does not match `{expected_type}`: {error}", response) from error
    if isinstance(built, JSONRPCError):
        raise JsonRpcResponseError(response, built.error, built.id_)
    return built.result


def _send_with_callbacks(request: Request, callbacks: Callbacks, timings: RequestTimings) -> Response:
    """
    Single attempt of the request - with callbacks of its stages (see `Callbacks`).

    When preparing, sending or processing the request raises, callbacks of errors are called in their order and the
    exception is raised afterwards.
    """
    response: Response | None = None
    try:
        for prepare_request in callbacks.prepare_request:
            request = prepare_request(request)
        started = time.perf_counter()
        try:
            response = send_http_request(request)
        finally:
            timings.attempts.append(time.perf_counter() - started)
        context = RequestContext(request=request, response=response, timings=timings)
        for process_response in callbacks.process_response:
            process_response(context)
    except Exception as error:
        context = RequestContext(request=request, response=response, exception=error, timings=timings)
        for error_callback in callbacks.error:
            error_callback(context)
        raise
    return response


async def _async_send_with_callbacks(request: Request, callbacks: AsyncCallbacks, timings: RequestTimings) -> Response:
    """Single attempt of the request - as `_send_with_callbacks`, the request is sent in a worker thread."""
    response: Response | None = None
    try:
        for prepare_request in callbacks.prepare_request:
            request = await _resolve(prepare_request(request))
        started = time.perf_counter()
        try:
            response = await asyncio.to_thread(send_http_request, request)
        finally:
            timings.attempts.append(time.perf_counter() - started)
        context = RequestContext(request=request, response=response, timings=timings)
        for process_response in callbacks.process_response:
            await _resolve(process_response(context))
    except Exception as error:
        context = RequestContext(request=request, response=response, exception=error, timings=timings)
        for error_callback in callbacks.error:
            await _resolve(error_callback(context))
        raise
    return response


def _reject_api_of_other_kind(
    api: object, other_kinds: tuple[type, ...], handle_name: str, matching_handle_name: str
) -> None:
    """Raise `TypeError` when the API is of the other kind (sync or async) than the handle - its calls never send."""
    if isinstance(api, other_kinds):
        raise TypeError(
            f"`{type(api).__name__}` can not be the API of `{handle_name}` - it is of the other kind (synchronous or"
            f" asynchronous) than the handle; use `{matching_handle_name}` for it"
        )


async def _resolve(result: T | Awaitable[T]) -> T:
    """Result of a callback - awaited when the callback is asynchronous (also an object with async `__call__`)."""
    if inspect.isawaitable(result):
        return cast("T", await result)
    return result


class SyncRemoteHandle(_RemoteHandle, SyncSendable, Generic[ApiT]):
    """
    Synchronous handle of a remote service - the owner of its APIs (e.g. generated API clients) sending their calls.

    Its API is built on `AbstractSyncApi` / `AbstractSyncApiCollection` - an asynchronous API raises `TypeError`.
    Clients generated by `templates/python_api_package.gitlab-ci.yml` are asynchronous - use `AsyncRemoteHandle`.

    Example:
    ```python
    # BalanceApi - an API client generated with `AbstractSyncApi` as its base class
    handle = SyncRemoteHandle(RemoteHandleSettings(http_endpoint=HttpUrl("https://api.hive.blog")), api=BalanceApi)
    delegations = handle.api.accounts_delegations("gtg")
    ```
    """

    def __init__(self, settings: RemoteHandleSettings, api: Callable[[SyncSendable], ApiT]) -> None:
        """
        Args:
            settings: The service and how requests are sent to it.
            api: Creates the API of the handle (an API class or a collection of APIs) for its owner - the handle or
                its batch.

        Raises:
            TypeError: The created API is asynchronous - it belongs to `AsyncRemoteHandle`.
        """
        super().__init__(settings)
        self.__api_factory = api
        self.__api = api(self)
        _reject_api_of_other_kind(
            self.__api, (AbstractAsyncApi, AbstractAsyncApiCollection), "SyncRemoteHandle", "AsyncRemoteHandle"
        )

    @property
    def api(self) -> ApiT:
        return self.__api

    def batch(self, *, delay_error_on_data_access: bool = False) -> SyncBatchHandle[ApiT]:
        """
        Batch of JSON-RPC calls - sent as one request when its context is left.

        Results of calls are available after the batch was sent. When a call failed, its error is raised when the
        context is left, or - with `delay_error_on_data_access` - when its result is accessed.
        """
        return SyncBatchHandle(
            owner=self, api=self.__api_factory, delay_error_on_data_access=delay_error_on_data_access
        )

    def _send(
        self,
        *,
        method: Methods,
        expected_type: type[ExpectResultT],
        data: str | None = None,
        url: HttpUrl | None = None,
        callbacks: Callbacks | None = None,
    ) -> JSONRPCResult[ExpectResultT]:
        response = self._send_request(url=self._merge_url(url), method=method, data=data, callbacks=callbacks)
        return JSONRPCResult(result=_built_result(response, expected_type, is_jsonrpc=_is_jsonrpc(data)))

    def _send_batch(self, *, data: str, callbacks: Callbacks) -> Response:
        """Send the request of a batch - its JSON-RPC errors are checked by the batch."""
        return self._send_request(url=self._merge_url(None), method="POST", data=data, callbacks=callbacks)

    def _send_request(
        self, *, url: HttpUrl, method: Methods, data: str | None, callbacks: Callbacks | None
    ) -> Response:
        """Send the request - again, while no response is received and retries are left."""
        all_callbacks = Callbacks.joined(Callbacks(process_response=[_check_response]), callbacks or Callbacks())
        timings = RequestTimings()
        retries_left = self.settings.max_retries
        while True:
            try:
                return _send_with_callbacks(self._prepare_request(url, method, data), all_callbacks, timings)
            except CommunicationError as error:
                retries_left = self._retries_left(error, retries_left)
                time.sleep(self.settings.period_between_retries.total_seconds())


class AsyncRemoteHandle(_RemoteHandle, AsyncSendable, Generic[ApiT]):
    """
    Asynchronous handle of a remote service - as `SyncRemoteHandle`, for asynchronous APIs.

    Its API is built on `AbstractAsyncApi` / `AbstractAsyncApiCollection` (as clients generated by
    `templates/python_api_package.gitlab-ci.yml`) - a synchronous API raises `TypeError`.

    Example:
    ```python
    handle = AsyncRemoteHandle(RemoteHandleSettings(http_endpoint=HttpUrl("https://api.hive.blog")), api=BalanceApi)
    delegations = await handle.api.accounts_delegations("gtg")
    ```
    """

    def __init__(self, settings: RemoteHandleSettings, api: Callable[[AsyncSendable], ApiT]) -> None:
        """
        Args:
            settings: The service and how requests are sent to it.
            api: Creates the API of the handle (an API class or a collection of APIs) for its owner - the handle or
                its batch.

        Raises:
            TypeError: The created API is synchronous - it belongs to `SyncRemoteHandle`.
        """
        super().__init__(settings)
        self.__api_factory = api
        self.__api = api(self)
        _reject_api_of_other_kind(
            self.__api, (AbstractSyncApi, AbstractSyncApiCollection), "AsyncRemoteHandle", "SyncRemoteHandle"
        )

    @property
    def api(self) -> ApiT:
        return self.__api

    def batch(self, *, delay_error_on_data_access: bool = False) -> AsyncBatchHandle[ApiT]:
        """Batch of JSON-RPC calls - as `SyncRemoteHandle.batch`, used with `async with`."""
        return AsyncBatchHandle(
            owner=self, api=self.__api_factory, delay_error_on_data_access=delay_error_on_data_access
        )

    async def _async_send(
        self,
        *,
        method: Methods,
        expected_type: type[ExpectResultT],
        data: str | None = None,
        url: HttpUrl | None = None,
        callbacks: AsyncCallbacks | None = None,
    ) -> JSONRPCResult[ExpectResultT]:
        response = await self._async_send_request(
            url=self._merge_url(url), method=method, data=data, callbacks=callbacks
        )
        return JSONRPCResult(result=_built_result(response, expected_type, is_jsonrpc=_is_jsonrpc(data)))

    async def _async_send_batch(self, *, data: str, callbacks: AsyncCallbacks) -> Response:
        """Send the request of a batch - its JSON-RPC errors are checked by the batch."""
        return await self._async_send_request(url=self._merge_url(None), method="POST", data=data, callbacks=callbacks)

    async def _async_send_request(
        self, *, url: HttpUrl, method: Methods, data: str | None, callbacks: AsyncCallbacks | None
    ) -> Response:
        """Send the request - again, while no response is received and retries are left."""
        all_callbacks = AsyncCallbacks.joined(
            AsyncCallbacks(process_response=[_check_response]), callbacks or AsyncCallbacks()
        )
        timings = RequestTimings()
        retries_left = self.settings.max_retries
        while True:
            try:
                return await _async_send_with_callbacks(
                    self._prepare_request(url, method, data), all_callbacks, timings
                )
            except CommunicationError as error:
                retries_left = self._retries_left(error, retries_left)
                await asyncio.sleep(self.settings.period_between_retries.total_seconds())
