from __future__ import annotations

import json

import pytest

from hiveio_api_client import AsyncRemoteHandle, HttpUrl, RemoteHandleSettings, SyncRemoteHandle
from hiveio_api_client.exceptions import HttpStatusError, InvalidResponseError, ResponseError
from tests.conftest import FakeService, GeneratedClients

BALANCE = {"account_name": "alice", "amount": 1000}


def _settings(service: FakeService) -> RemoteHandleSettings:
    return RemoteHandleSettings(http_endpoint=service.url, max_retries=0)


async def test_async_rest_call_returns_the_response_model(generated: GeneratedClients, service: FakeService) -> None:
    # ARRANGE
    service.reply = lambda _: (200, json.dumps(BALANCE))
    handle = AsyncRemoteHandle(_settings(service), api=generated.async_rest.SampleApi)

    # ACT
    balance = await handle.api.accounts_balance("alice", coin_type="HIVE")

    # ASSERT
    assert type(balance).__name__ == "Balance"
    assert (balance.account_name, balance.amount) == ("alice", 1000)
    assert service.requests[0].method == "GET"
    assert service.requests[0].path == "/sample-api/accounts/alice/balance?coin-type=HIVE"


def test_sync_rest_call_returns_the_response_model(generated: GeneratedClients, service: FakeService) -> None:
    # ARRANGE
    service.reply = lambda _: (200, json.dumps(BALANCE))
    handle = SyncRemoteHandle(_settings(service), api=generated.sync_rest.SampleApi)

    # ACT
    balance = handle.api.accounts_balance("alice")

    # ASSERT
    assert (balance.account_name, balance.amount) == ("alice", 1000)
    assert service.requests[0].path == "/sample-api/accounts/alice/balance"


def test_rest_call_is_sent_to_the_address_of_the_endpoint(generated: GeneratedClients, service: FakeService) -> None:
    # ARRANGE - the path of the endpoint of the settings is replaced by the path of the REST endpoint
    service.reply = lambda _: (200, json.dumps(BALANCE))
    endpoint = HttpUrl(f"{service.url}/ignored-path")
    handle = SyncRemoteHandle(
        RemoteHandleSettings(http_endpoint=endpoint, max_retries=0), api=generated.sync_rest.SampleApi
    )

    # ACT
    handle.api.accounts_balance("bob")

    # ASSERT
    assert service.requests[0].path == "/sample-api/accounts/bob/balance"


async def test_http_error_status_raises_http_status_error(generated: GeneratedClients, service: FakeService) -> None:
    # ARRANGE
    service.reply = lambda _: (404, json.dumps({"code": "P0001", "message": "Account 'nobody' does not exist"}))
    handle = AsyncRemoteHandle(_settings(service), api=generated.async_rest.SampleApi)

    # ACT & ASSERT
    with pytest.raises(HttpStatusError) as error:
        await handle.api.accounts_balance("nobody")
    assert error.value.status_code == 404
    assert "does not exist" in error.value.response.body
    assert len(service.requests) == 1, "Responses with errors are not retried"


@pytest.mark.parametrize(
    "body",
    [
        pytest.param("<html>Bad gateway</html>", id="not JSON"),
        pytest.param(json.dumps({"account_name": "alice"}), id="result not matching the model"),
    ],
)
def test_invalid_response_raises_invalid_response_error(
    generated: GeneratedClients, service: FakeService, body: str
) -> None:
    # ARRANGE
    service.reply = lambda _: (200, body)
    handle = SyncRemoteHandle(_settings(service), api=generated.sync_rest.SampleApi)

    # ACT & ASSERT
    with pytest.raises(InvalidResponseError) as error:
        handle.api.accounts_balance("alice")
    assert isinstance(error.value, ResponseError)
    assert error.value.response.body == body
