from __future__ import annotations

from typing import Any

import pytest

from hiveio_api_client import (
    AbstractAsyncApiCollection,
    AbstractSyncApiCollection,
    AsyncRemoteHandle,
    AsyncSendable,
    HttpUrl,
    RemoteHandleSettings,
    SyncRemoteHandle,
    SyncSendable,
)
from tests.conftest import GeneratedClients

SETTINGS = RemoteHandleSettings(http_endpoint=HttpUrl("http://127.0.0.1:1"))


class _SyncCollectionOfSampleApi(AbstractSyncApiCollection):
    sample_api: Any


class _AsyncCollectionOfSampleApi(AbstractAsyncApiCollection):
    sample_api: Any


def _sync_collection(generated: GeneratedClients) -> type[_SyncCollectionOfSampleApi]:
    class SyncCollection(_SyncCollectionOfSampleApi):
        def __init__(self, owner: SyncSendable) -> None:
            super().__init__(owner)
            self.sample_api = generated.sync_jsonrpc.SampleApi(owner)

    return SyncCollection


def _async_collection(generated: GeneratedClients) -> type[_AsyncCollectionOfSampleApi]:
    class AsyncCollection(_AsyncCollectionOfSampleApi):
        def __init__(self, owner: AsyncSendable) -> None:
            super().__init__(owner)
            self.sample_api = generated.async_jsonrpc.SampleApi(owner)

    return AsyncCollection


def test_sync_handle_accepts_sync_api_and_collection(generated: GeneratedClients) -> None:
    # ACT
    api_handle = SyncRemoteHandle(SETTINGS, api=generated.sync_jsonrpc.SampleApi)
    collection_handle = SyncRemoteHandle(SETTINGS, api=_sync_collection(generated))

    # ASSERT
    assert isinstance(api_handle.api, generated.sync_jsonrpc.SampleApi)
    assert isinstance(collection_handle.api.sample_api, generated.sync_jsonrpc.SampleApi)


def test_async_handle_accepts_async_api_and_collection(generated: GeneratedClients) -> None:
    # ACT
    api_handle = AsyncRemoteHandle(SETTINGS, api=generated.async_jsonrpc.SampleApi)
    collection_handle = AsyncRemoteHandle(SETTINGS, api=_async_collection(generated))

    # ASSERT
    assert isinstance(api_handle.api, generated.async_jsonrpc.SampleApi)
    assert isinstance(collection_handle.api.sample_api, generated.async_jsonrpc.SampleApi)


@pytest.mark.parametrize("api_of", ["async_rest", "async_jsonrpc", "async_collection", "async_factory"])
def test_sync_handle_rejects_async_api(generated: GeneratedClients, api_of: str) -> None:
    # ARRANGE
    apis: dict[str, Any] = {
        "async_rest": generated.async_rest.SampleApi,
        "async_jsonrpc": generated.async_jsonrpc.SampleApi,
        "async_collection": _async_collection(generated),
        "async_factory": lambda owner: generated.async_jsonrpc.SampleApi(owner),
    }
    expected_name = "AsyncCollection" if api_of == "async_collection" else "SampleApi"

    # ACT & ASSERT
    with pytest.raises(TypeError, match="AsyncRemoteHandle") as error:
        SyncRemoteHandle(SETTINGS, api=apis[api_of])
    assert f"`{expected_name}`" in str(error.value)


@pytest.mark.parametrize("api_of", ["sync_rest", "sync_jsonrpc", "sync_collection", "sync_factory"])
def test_async_handle_rejects_sync_api(generated: GeneratedClients, api_of: str) -> None:
    # ARRANGE
    apis: dict[str, Any] = {
        "sync_rest": generated.sync_rest.SampleApi,
        "sync_jsonrpc": generated.sync_jsonrpc.SampleApi,
        "sync_collection": _sync_collection(generated),
        "sync_factory": lambda owner: generated.sync_jsonrpc.SampleApi(owner),
    }
    expected_name = "SyncCollection" if api_of == "sync_collection" else "SampleApi"

    # ACT & ASSERT
    with pytest.raises(TypeError, match="SyncRemoteHandle") as error:
        AsyncRemoteHandle(SETTINGS, api=apis[api_of])
    assert f"`{expected_name}`" in str(error.value)
