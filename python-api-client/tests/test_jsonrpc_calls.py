from __future__ import annotations

import json

import pytest

from hiveio_api_client import AsyncRemoteHandle, RemoteHandleSettings, SyncRemoteHandle
from hiveio_api_client.exceptions import (
    HttpStatusError,
    InvalidResponseError,
    JsonRpcResponseError,
    ResponseNotReadyError,
    UnsupportedBatchCallError,
)
from tests.conftest import FakeService, GeneratedClients

RESULTS: dict[str, object] = {
    "sample_api.get_balance": {"account_name": "alice", "amount": 1000},
    "sample_api.get_head_block": {"block_num": 42},
}
UNKNOWN_ACCOUNT = {"code": -32000, "message": "Account `nobody` does not exist"}


def _settings(service: FakeService) -> RemoteHandleSettings:
    return RemoteHandleSettings(http_endpoint=service.url, max_retries=0)


async def test_async_jsonrpc_call_returns_the_response_model(generated: GeneratedClients, service: FakeService) -> None:
    # ARRANGE
    service.answer_jsonrpc(RESULTS)
    handle = AsyncRemoteHandle(_settings(service), api=generated.async_jsonrpc.SampleApi)

    # ACT
    balance = await handle.api.get_balance(account_name="alice")

    # ASSERT
    assert type(balance).__name__ == "GetBalanceResponse"
    assert (balance.account_name, balance.amount) == ("alice", 1000)
    request = service.requests[0]
    assert (request.method, request.path) == ("POST", "/")
    assert request.json == {
        "id": 0,
        "jsonrpc": "2.0",
        "method": "sample_api.get_balance",
        "params": {"account_name": "alice"},
    }


def test_sync_jsonrpc_call_returns_the_response_model(generated: GeneratedClients, service: FakeService) -> None:
    # ARRANGE
    service.answer_jsonrpc(RESULTS)
    handle = SyncRemoteHandle(_settings(service), api=generated.sync_jsonrpc.SampleApi)

    # ACT
    head_block = handle.api.get_head_block()

    # ASSERT
    assert head_block.block_num == 42


async def test_async_batch_returns_results_of_both_calls(generated: GeneratedClients, service: FakeService) -> None:
    # ARRANGE
    service.answer_jsonrpc(RESULTS)
    handle = AsyncRemoteHandle(_settings(service), api=generated.async_jsonrpc.SampleApi)

    # ACT
    async with handle.batch() as batch:
        balance = await batch.api.get_balance(account_name="alice")
        head_block = await batch.api.get_head_block()

    # ASSERT
    assert (balance.account_name, balance.amount) == ("alice", 1000)
    assert head_block.block_num == 42
    assert len(service.requests) == 1, "Calls of a batch are sent as one request"
    assert [(call["id"], call["method"]) for call in service.requests[0].json] == [
        (0, "sample_api.get_balance"),
        (1, "sample_api.get_head_block"),
    ]


def test_sync_batch_returns_results_of_both_calls(generated: GeneratedClients, service: FakeService) -> None:
    # ARRANGE
    service.answer_jsonrpc(RESULTS)
    handle = SyncRemoteHandle(_settings(service), api=generated.sync_jsonrpc.SampleApi)

    # ACT
    with handle.batch() as batch:
        balance = batch.api.get_balance(account_name="alice")
        head_block = batch.api.get_head_block()

    # ASSERT
    assert balance.amount == 1000
    assert head_block.block_num == 42


def test_results_of_a_batch_are_not_ready_before_it_is_sent(generated: GeneratedClients, service: FakeService) -> None:
    # ARRANGE
    service.answer_jsonrpc(RESULTS)
    handle = SyncRemoteHandle(_settings(service), api=generated.sync_jsonrpc.SampleApi)

    # ACT & ASSERT
    with handle.batch() as batch:
        head_block = batch.api.get_head_block()
        with pytest.raises(ResponseNotReadyError):
            _ = head_block.block_num
    assert head_block.block_num == 42


async def test_jsonrpc_error_raises_jsonrpc_response_error(generated: GeneratedClients, service: FakeService) -> None:
    # ARRANGE
    service.answer_jsonrpc(RESULTS, errors={"sample_api.get_balance": UNKNOWN_ACCOUNT})
    handle = AsyncRemoteHandle(_settings(service), api=generated.async_jsonrpc.SampleApi)

    # ACT & ASSERT
    with pytest.raises(JsonRpcResponseError) as error:
        await handle.api.get_balance(account_name="nobody")
    assert error.value.error == UNKNOWN_ACCOUNT
    assert error.value.request_id == 0


def test_jsonrpc_error_with_http_error_status_raises_jsonrpc_response_error(
    generated: GeneratedClients, service: FakeService
) -> None:
    # ARRANGE
    service.reply = lambda _: (500, json.dumps({"jsonrpc": "2.0", "id": 0, "error": UNKNOWN_ACCOUNT}))
    handle = SyncRemoteHandle(_settings(service), api=generated.sync_jsonrpc.SampleApi)

    # ACT & ASSERT
    with pytest.raises(JsonRpcResponseError) as error:
        handle.api.get_balance(account_name="nobody")
    assert error.value.error == UNKNOWN_ACCOUNT


def test_http_error_status_of_jsonrpc_call_raises_http_status_error(
    generated: GeneratedClients, service: FakeService
) -> None:
    # ARRANGE
    service.reply = lambda _: (502, "Bad gateway")
    handle = SyncRemoteHandle(_settings(service), api=generated.sync_jsonrpc.SampleApi)

    # ACT & ASSERT
    with pytest.raises(HttpStatusError) as error:
        handle.api.get_head_block()
    assert error.value.status_code == 502


async def test_error_of_a_call_of_a_batch_is_raised_when_the_batch_is_left(
    generated: GeneratedClients, service: FakeService
) -> None:
    # ARRANGE
    service.answer_jsonrpc(RESULTS, errors={"sample_api.get_balance": UNKNOWN_ACCOUNT})
    handle = AsyncRemoteHandle(_settings(service), api=generated.async_jsonrpc.SampleApi)

    # ACT & ASSERT
    with pytest.raises(JsonRpcResponseError) as error:
        async with handle.batch() as batch:
            await batch.api.get_head_block()
            await batch.api.get_balance(account_name="nobody")
    assert error.value.error == UNKNOWN_ACCOUNT
    assert error.value.request_id == 1


def test_delayed_error_of_a_call_of_a_batch_is_raised_when_its_result_is_accessed(
    generated: GeneratedClients, service: FakeService
) -> None:
    # ARRANGE
    service.answer_jsonrpc(RESULTS, errors={"sample_api.get_balance": UNKNOWN_ACCOUNT})
    handle = SyncRemoteHandle(_settings(service), api=generated.sync_jsonrpc.SampleApi)

    # ACT
    with handle.batch(delay_error_on_data_access=True) as batch:
        head_block = batch.api.get_head_block()
        balance = batch.api.get_balance(account_name="nobody")

    # ASSERT
    assert head_block.block_num == 42
    with pytest.raises(JsonRpcResponseError):
        _ = balance.amount


def test_batch_response_not_answering_each_call_raises_invalid_response_error(
    generated: GeneratedClients, service: FakeService
) -> None:
    # ARRANGE
    service.reply = lambda _: (
        200,
        json.dumps([{"jsonrpc": "2.0", "id": 0, "result": RESULTS["sample_api.get_head_block"]}]),
    )
    handle = SyncRemoteHandle(_settings(service), api=generated.sync_jsonrpc.SampleApi)

    # ACT & ASSERT
    with pytest.raises(InvalidResponseError), handle.batch() as batch:
        batch.api.get_head_block()
        batch.api.get_head_block()


def test_rest_calls_can_not_be_batched(generated: GeneratedClients, service: FakeService) -> None:
    # ARRANGE
    handle = SyncRemoteHandle(_settings(service), api=generated.sync_rest.SampleApi)

    # ACT & ASSERT
    with pytest.raises(UnsupportedBatchCallError), handle.batch() as batch:
        batch.api.accounts_balance("alice")
    assert service.requests == []
