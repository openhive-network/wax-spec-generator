from __future__ import annotations

import dataclasses
import socket
from collections.abc import Callable, Iterator
from datetime import timedelta
from typing import TypeVar, cast

import pytest

from hiveio_api_client import (
    AsyncRemoteHandle,
    HttpUrl,
    RemoteHandleSettings,
    Request,
    RequestContext,
    SyncRemoteHandle,
    ValueCodec,
    install_value_codec,
)
from hiveio_api_client.exceptions import CommunicationError, HttpStatusError, TimeoutExceededError
from tests.conftest import FakeService, GeneratedClients

HEAD_BLOCK = {"sample_api.get_head_block": {"block_num": 42}}

T = TypeVar("T")


def _tagging_value_builder(annotation: type[T]) -> Callable[[object], T]:
    """Builder of results of tests - tags the value with the name of the expected type instead of building it."""
    return lambda value: cast("T", ("built", annotation.__name__, value))


def _unused_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port: int = sock.getsockname()[1]
        return port


def test_request_without_response_is_retried_and_raises_communication_error(generated: GeneratedClients) -> None:
    # ARRANGE
    settings = RemoteHandleSettings(
        http_endpoint=HttpUrl(f"http://127.0.0.1:{_unused_port()}"),
        max_retries=2,
        period_between_retries=timedelta(0),
    )
    handle = SyncRemoteHandle(settings, api=generated.sync_jsonrpc.SampleApi)
    failed_attempts: list[RequestContext] = []
    handle.api.callbacks.error.append(failed_attempts.append)

    # ACT & ASSERT
    with pytest.raises(CommunicationError):
        handle.api.get_head_block()
    assert len(failed_attempts) == 3, "The first attempt and `max_retries` retries"
    assert failed_attempts[-1].attempt == 3


async def test_request_answered_after_timeout_raises_timeout_exceeded_error(
    generated: GeneratedClients, service: FakeService
) -> None:
    # ARRANGE
    service.answer_jsonrpc(HEAD_BLOCK)
    service.delay = 1
    settings = RemoteHandleSettings(http_endpoint=service.url, timeout=timedelta(seconds=0.1), max_retries=0)
    handle = AsyncRemoteHandle(settings, api=generated.async_jsonrpc.SampleApi)

    # ACT & ASSERT
    with pytest.raises(TimeoutExceededError) as error:
        await handle.api.get_head_block()
    assert error.value.timeout_secs == pytest.approx(0.1)


async def test_callbacks_prepare_requests_and_process_responses(
    generated: GeneratedClients, service: FakeService
) -> None:
    # ARRANGE
    service.answer_jsonrpc(HEAD_BLOCK)
    handle = AsyncRemoteHandle(
        RemoteHandleSettings(http_endpoint=service.url, max_retries=0), api=generated.async_jsonrpc.SampleApi
    )
    statuses: list[int] = []

    async def authorize(request: Request) -> Request:
        return dataclasses.replace(request, headers=request.headers | {"Authorization": "Bearer token"})

    handle.api.get_head_block.callbacks.prepare_request.append(authorize)
    handle.api.callbacks.process_response.append(lambda context: statuses.append(context.response.status_code))

    # ACT
    await handle.api.get_head_block()

    # ASSERT
    assert service.requests[0].headers["Authorization"] == "Bearer token"
    assert statuses == [200]


def test_error_callbacks_get_errors_of_responses(generated: GeneratedClients, service: FakeService) -> None:
    # ARRANGE
    service.reply = lambda _: (503, "Service unavailable")
    handle = SyncRemoteHandle(
        RemoteHandleSettings(http_endpoint=service.url, max_retries=0), api=generated.sync_jsonrpc.SampleApi
    )
    errors: list[Exception | None] = []
    handle.api.callbacks.error.append(lambda context: errors.append(context.exception))

    # ACT & ASSERT
    with pytest.raises(HttpStatusError):
        handle.api.get_head_block()
    assert len(errors) == 1
    assert isinstance(errors[0], HttpStatusError)


@pytest.fixture
def codec_of_tests() -> Iterator[Callable[[ValueCodec], None]]:
    previous: list[ValueCodec] = []
    yield lambda codec: previous.append(install_value_codec(codec))
    for codec in reversed(previous):
        install_value_codec(codec)


def test_installed_value_codec_converts_parameters_and_builds_results(
    generated: GeneratedClients, service: FakeService, codec_of_tests: Callable[[ValueCodec], None]
) -> None:
    # ARRANGE
    service.answer_jsonrpc({"sample_api.get_balance": {"account_name": "alice", "amount": 1000}})
    handle = SyncRemoteHandle(
        RemoteHandleSettings(http_endpoint=service.url, max_retries=0), api=generated.sync_jsonrpc.SampleApi
    )
    codec_of_tests(
        ValueCodec(
            to_api_builtins=lambda value, testnet: {"account_name": "converted", "testnet": testnet()},
            value_builder=_tagging_value_builder,
        )
    )

    # ACT
    result = handle.api.get_balance(account_name="alice")

    # ASSERT
    assert service.requests[0].json["params"] == {"account_name": "converted", "testnet": False}
    assert result == ("built", "GetBalanceResponse", {"account_name": "alice", "amount": 1000})


def test_json_default_of_the_codec_serializes_unknown_parameters(
    generated: GeneratedClients, service: FakeService, codec_of_tests: Callable[[ValueCodec], None]
) -> None:
    # ARRANGE
    class AccountName:
        def __init__(self, name: str) -> None:
            self.name = name

    def account_name_default(value: object) -> object:
        if isinstance(value, AccountName):
            return value.name
        raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")

    service.answer_jsonrpc({"sample_api.get_balance": {"account_name": "alice", "amount": 1000}})
    handle = SyncRemoteHandle(
        RemoteHandleSettings(http_endpoint=service.url, max_retries=0), api=generated.sync_jsonrpc.SampleApi
    )
    codec_of_tests(
        ValueCodec(
            to_api_builtins=lambda value, testnet: value,
            json_default=account_name_default,
        )
    )

    # ACT
    handle.api.get_balance(account_name=AccountName("alice"))

    # ASSERT
    assert service.requests[0].json["params"] == {"account_name": "alice"}
