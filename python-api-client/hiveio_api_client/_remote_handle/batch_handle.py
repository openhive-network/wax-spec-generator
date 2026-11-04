from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Final, Generic, Protocol, Self, TypeVar, cast

from hiveio_api_client._apis.abc.sendable import AsyncSendable, SyncSendable
from hiveio_api_client._communication.abc.communicator_models import AsyncCallbacks, Callbacks
from hiveio_api_client._communication.jsonrpc import JSONRPCResult
from hiveio_api_client._values import value_builder
from hiveio_api_client.exceptions import (
    InvalidResponseError,
    JsonRpcResponseError,
    ResponseError,
    ResponseNotReadyError,
    UnsupportedBatchCallError,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator, Mapping
    from types import TracebackType

    from hiveio_api_client._communication.abc.communicator_models import Methods, Response
    from hiveio_api_client._communication.jsonrpc import ExpectResultT
    from hiveio_api_client._communication.url import HttpUrl

ApiT = TypeVar("ApiT")
CallbacksT = TypeVar("CallbacksT", Callbacks, AsyncCallbacks)
T = TypeVar("T")

_NOT_READY: Final[object] = object()


class _DelayedResult:
    """
    Result of a call of a batch - stands for the built result once the batch was sent.

    Attributes, items, iteration, length, truth and equality are those of the result. Accessing them before the batch
    was sent raises `ResponseNotReadyError`, after the call failed - its error.
    """

    def __init__(self) -> None:
        object.__setattr__(self, "_value", _NOT_READY)
        object.__setattr__(self, "_error", None)

    def _set_value(self, value: object) -> None:
        object.__setattr__(self, "_value", value)

    def _set_error(self, error: ResponseError) -> None:
        object.__setattr__(self, "_error", error)

    def _resolved(self) -> Any:  # the result of the call - of the type expected by its endpoint
        if self._error is not None:
            raise self._error
        if self._value is _NOT_READY:
            raise ResponseNotReadyError("The batch was not sent yet - results are available when it is left")
        return self._value

    def __getattr__(self, name: str) -> Any:
        return getattr(self._resolved(), name)

    def __setattr__(self, name: str, value: object) -> None:
        setattr(self._resolved(), name, value)

    def __getitem__(self, key: object) -> Any:
        return self._resolved()[key]

    def __iter__(self) -> Iterator[Any]:
        return iter(self._resolved())

    def __len__(self) -> int:
        return len(self._resolved())

    def __bool__(self) -> bool:
        return bool(self._resolved())

    def __eq__(self, other: object) -> bool:
        return bool(self._resolved() == other)

    def __hash__(self) -> int:
        return hash(self._resolved())

    def __repr__(self) -> str:
        if self._error is None and self._value is _NOT_READY:
            return "<result of a batch not sent yet>"
        return repr(self._resolved())


@dataclass
class _Call:
    data: str
    expected_type: type[object]
    result: _DelayedResult = field(default_factory=_DelayedResult)


class _Batch(Generic[CallbacksT]):
    """Calls of a batch and their results - common to synchronous and asynchronous batches."""

    def __init__(self, *, delay_error_on_data_access: bool) -> None:
        self.__delay_error_on_data_access = delay_error_on_data_access
        self.__calls: list[_Call] = []
        self.__callbacks: list[CallbacksT] = []

    def _id_for_jsonrpc_request(self) -> int:
        """Ids of calls are their indexes in the batch."""
        return len(self.__calls)

    def _add_call(
        self,
        *,
        data: str | None,
        url: HttpUrl | None,
        expected_type: type[ExpectResultT],
        callbacks: CallbacksT | None,
    ) -> JSONRPCResult[ExpectResultT]:
        if url is not None or data is None:
            raise UnsupportedBatchCallError("Only JSON-RPC calls can be sent in a batch, not calls of REST endpoints")
        call = _Call(data=data, expected_type=expected_type)
        self.__calls.append(call)
        if callbacks is not None:
            self.__callbacks.append(callbacks)
        return JSONRPCResult(result=cast("ExpectResultT", call.result))

    def _has_calls(self) -> bool:
        return bool(self.__calls)

    def _body(self) -> str:
        return "[" + ",".join(call.data for call in self.__calls) + "]"

    def _request_callbacks(self, callbacks_type: type[CallbacksT]) -> CallbacksT:
        """Callbacks of all calls of the batch - each callback once, in the order of its first occurrence."""
        joined = callbacks_type.joined(*self.__callbacks)
        return callbacks_type(
            prepare_request=_unique(joined.prepare_request),
            process_response=_unique(joined.process_response),
            error=_unique(joined.error),
        )

    def _set_results(self, response: Response) -> None:
        """
        Give results (or errors) of the response to the calls of the batch.

        Raises:
            InvalidResponseError: The response does not answer each call of the batch.
            ResponseError: The error of the first failed call - unless errors are delayed until results are accessed.
        """
        payload = response.json
        if not isinstance(payload, list) or len(payload) != len(self.__calls):
            raise InvalidResponseError(f"Response does not answer the calls of the batch: {response.body}", response)
        answers = {item.get("id"): item for item in payload if isinstance(item, dict)}
        errors: list[ResponseError] = []
        for call_id, call in enumerate(self.__calls):
            answer = answers.get(call_id)
            if answer is None:
                raise InvalidResponseError(f"No response to the call {call_id} of the batch: {response.body}", response)
            error = _set_result(call, answer, response)
            if error is not None:
                errors.append(error)
        if errors and not self.__delay_error_on_data_access:
            raise errors[0]


def _set_result(call: _Call, answer: Mapping[str, object], response: Response) -> ResponseError | None:
    """Give its result to the call - or the error of its answer, which is also returned."""
    error: ResponseError
    if "result" not in answer:
        error = JsonRpcResponseError.of_payload(response, answer)
    else:
        try:
            call.result._set_value(value_builder(call.expected_type)(answer["result"]))
        except ValueError as build_error:
            error = InvalidResponseError(f"Result does not match `{call.expected_type}`: {build_error}", response)
        else:
            return None
    call.result._set_error(error)
    return error


def _unique(items: list[T]) -> list[T]:
    return list({id(item): item for item in items}.values())


class _SyncBatchOwner(Protocol):
    def is_testnet(self) -> bool: ...

    def _send_batch(self, *, data: str, callbacks: Callbacks) -> Response: ...


class _AsyncBatchOwner(Protocol):
    def is_testnet(self) -> bool: ...

    async def _async_send_batch(self, *, data: str, callbacks: AsyncCallbacks) -> Response: ...


class SyncBatchHandle(_Batch[Callbacks], SyncSendable, Generic[ApiT]):
    """
    Batch of JSON-RPC calls of a synchronous handle (see `SyncRemoteHandle.batch`) - sent when its context is left.

    The request of the batch is sent with callbacks of all its calls, each callback once.

    Example:
    ```python
    with handle.batch() as batch:
        first = batch.api.first_endpoint(...)
        second = batch.api.second_endpoint(...)
    print(first.some_field, second.other_field)
    ```
    """

    def __init__(
        self,
        *,
        owner: _SyncBatchOwner,
        api: Callable[[SyncSendable], ApiT],
        delay_error_on_data_access: bool = False,
    ) -> None:
        super().__init__(delay_error_on_data_access=delay_error_on_data_access)
        self.__owner = owner
        self.__api = api(self)

    @property
    def api(self) -> ApiT:
        return self.__api

    def is_testnet(self) -> bool:
        return self.__owner.is_testnet()

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self, exc_type: type[BaseException] | None, exc: BaseException | None, traceback: TracebackType | None
    ) -> None:
        if exc_type is None and self._has_calls():
            callbacks = self._request_callbacks(Callbacks)
            self._set_results(self.__owner._send_batch(data=self._body(), callbacks=callbacks))

    def _send(
        self,
        *,
        method: Methods,
        expected_type: type[ExpectResultT],
        data: str | None = None,
        url: HttpUrl | None = None,
        callbacks: Callbacks | None = None,
    ) -> JSONRPCResult[ExpectResultT]:
        return self._add_call(data=data, url=url, expected_type=expected_type, callbacks=callbacks)


class AsyncBatchHandle(_Batch[AsyncCallbacks], AsyncSendable, Generic[ApiT]):
    """
    Batch of JSON-RPC calls of an asynchronous handle (see `AsyncRemoteHandle.batch`) - as `SyncBatchHandle`.

    Example:
    ```python
    async with handle.batch() as batch:
        first = await batch.api.first_endpoint(...)
        second = await batch.api.second_endpoint(...)
    print(first.some_field, second.other_field)
    ```
    """

    def __init__(
        self,
        *,
        owner: _AsyncBatchOwner,
        api: Callable[[AsyncSendable], ApiT],
        delay_error_on_data_access: bool = False,
    ) -> None:
        super().__init__(delay_error_on_data_access=delay_error_on_data_access)
        self.__owner = owner
        self.__api = api(self)

    @property
    def api(self) -> ApiT:
        return self.__api

    def is_testnet(self) -> bool:
        return self.__owner.is_testnet()

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self, exc_type: type[BaseException] | None, exc: BaseException | None, traceback: TracebackType | None
    ) -> None:
        if exc_type is None and self._has_calls():
            callbacks = self._request_callbacks(AsyncCallbacks)
            self._set_results(await self.__owner._async_send_batch(data=self._body(), callbacks=callbacks))

    async def _async_send(
        self,
        *,
        method: Methods,
        expected_type: type[ExpectResultT],
        data: str | None = None,
        url: HttpUrl | None = None,
        callbacks: AsyncCallbacks | None = None,
    ) -> JSONRPCResult[ExpectResultT]:
        return self._add_call(data=data, url=url, expected_type=expected_type, callbacks=callbacks)
