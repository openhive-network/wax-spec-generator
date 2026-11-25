from __future__ import annotations

from collections.abc import Mapping

import pytest

from hiveio_api_client import (
    AbstractSyncApiCollection,
    AsyncRemoteHandle,
    RemoteHandleSettings,
    RequestContext,
    SyncRemoteHandle,
    SyncSendable,
    compiled_validation_mask_of,
    copy_validation_masks,
)
from tests.conftest import FakeService, GeneratedClients

RESULTS: dict[str, object] = {
    "sample_api.get_balance": {"account_name": "alice", "amount": 1000},
    "sample_api.get_head_block": {"block_num": 42},
}
BALANCE = "sample_api.get_balance"
HEAD_BLOCK = "sample_api.get_head_block"


def _settings(service: FakeService) -> RemoteHandleSettings:
    return RemoteHandleSettings(http_endpoint=service.url, max_retries=0)


class MaskRecorder:
    """Response callback recording compiled masks of the endpoints visible to validators of each request."""

    def __init__(self) -> None:
        self.seen: list[dict[str, object | None]] = []

    def __call__(self, context: RequestContext, /) -> None:
        self.seen.append({method: compiled_validation_mask_of(method) for method in (BALANCE, HEAD_BLOCK)})


def _compiling(api_class: type) -> type:
    """The API class compiling masks - to a tuple, refusing masks with the key `wrong`."""

    class CompilingApi(api_class):  # type: ignore[misc]  # a generated class given at run time
        def _compile_validation_mask(self, endpoint_name: str, mask: Mapping[str, object]) -> object:
            if "wrong" in mask:
                raise ValueError(f"wrong mask of {endpoint_name}")
            return ("compiled", endpoint_name, tuple(mask))

    CompilingApi.__name__ = CompilingApi.__qualname__ = api_class.__name__
    return CompilingApi


async def test_mask_is_given_to_validators_of_requests_of_its_endpoint(
    generated: GeneratedClients, service: FakeService
) -> None:
    # ARRANGE
    service.answer_jsonrpc(RESULTS)
    handle = AsyncRemoteHandle(_settings(service), api=generated.async_jsonrpc.SampleApi)
    recorder = MaskRecorder()
    handle.api.callbacks.process_response.append(recorder)

    # ACT
    handle.api.get_balance.set_validation_mask({"amount": True})
    await handle.api.get_balance(account_name="alice")
    await handle.api.get_head_block()

    # ASSERT
    assert recorder.seen == [{BALANCE: {"amount": True}, HEAD_BLOCK: None}, {BALANCE: None, HEAD_BLOCK: None}]
    assert compiled_validation_mask_of(BALANCE) is None, "the mask is given only while a request is sent"


def test_mask_of_synchronous_endpoint_is_given_to_validators(generated: GeneratedClients, service: FakeService) -> None:
    # ARRANGE
    service.answer_jsonrpc(RESULTS)
    handle = SyncRemoteHandle(_settings(service), api=generated.sync_jsonrpc.SampleApi)
    recorder = MaskRecorder()
    handle.api.callbacks.process_response.append(recorder)

    # ACT
    handle.api.get_head_block.set_validation_mask({"block_num": True})
    handle.api.get_head_block()

    # ASSERT
    assert recorder.seen == [{BALANCE: None, HEAD_BLOCK: {"block_num": True}}]


async def test_mask_is_compiled_by_the_api_when_it_is_set(generated: GeneratedClients, service: FakeService) -> None:
    # ARRANGE
    service.answer_jsonrpc(RESULTS)
    handle = AsyncRemoteHandle(_settings(service), api=_compiling(generated.async_jsonrpc.SampleApi))
    recorder = MaskRecorder()
    handle.api.callbacks.process_response.append(recorder)
    endpoint = handle.api.get_balance

    # ACT
    endpoint.set_validation_mask({"amount": True})
    await endpoint(account_name="alice")

    # ASSERT
    compiled = ("compiled", "get_balance", ("amount",))
    assert (endpoint.validation_mask, endpoint.compiled_validation_mask) == ({"amount": True}, compiled)
    assert recorder.seen == [{BALANCE: compiled, HEAD_BLOCK: None}]


def test_wrong_mask_raises_when_it_is_set_and_the_previous_mask_stays(
    generated: GeneratedClients, service: FakeService
) -> None:
    # ARRANGE
    handle = SyncRemoteHandle(_settings(service), api=_compiling(generated.sync_jsonrpc.SampleApi))
    endpoint = handle.api.get_balance
    endpoint.set_validation_mask({"amount": True})

    # ACT & ASSERT
    with pytest.raises(ValueError, match="wrong mask of get_balance"):
        endpoint.set_validation_mask({"wrong": True})
    assert endpoint.validation_mask == {"amount": True}


def test_mask_is_removed_by_none(generated: GeneratedClients, service: FakeService) -> None:
    # ARRANGE
    handle = SyncRemoteHandle(_settings(service), api=generated.sync_jsonrpc.SampleApi)
    endpoint = handle.api.get_balance
    endpoint.set_validation_mask({"amount": True})

    # ACT
    endpoint.set_validation_mask(None)

    # ASSERT
    assert (endpoint.validation_mask, endpoint.compiled_validation_mask) == (None, None)


def test_masks_are_kept_by_each_instance_of_the_api(generated: GeneratedClients, service: FakeService) -> None:
    # ARRANGE
    first = SyncRemoteHandle(_settings(service), api=generated.sync_jsonrpc.SampleApi)
    second = SyncRemoteHandle(_settings(service), api=generated.sync_jsonrpc.SampleApi)

    # ACT
    first.api.get_balance.set_validation_mask({"amount": True})

    # ASSERT
    assert second.api.get_balance.validation_mask is None


async def test_batch_gives_masks_of_its_calls_to_validators(generated: GeneratedClients, service: FakeService) -> None:
    # ARRANGE
    service.answer_jsonrpc(RESULTS)
    handle = AsyncRemoteHandle(_settings(service), api=generated.async_jsonrpc.SampleApi)
    recorder = MaskRecorder()
    handle.api.callbacks.process_response.append(recorder)

    # ACT
    async with handle.batch() as batch:
        batch.api.get_balance.set_validation_mask({"amount": True})
        batch.api.callbacks.process_response.append(recorder)
        await batch.api.get_balance(account_name="alice")
        await batch.api.get_head_block()

    # ASSERT
    assert len(service.requests) == 1
    assert recorder.seen == [{BALANCE: {"amount": True}, HEAD_BLOCK: None}], "callbacks of a batch are called once"
    assert compiled_validation_mask_of(BALANCE) is None


async def test_batch_has_masks_of_endpoints_of_its_handle(generated: GeneratedClients, service: FakeService) -> None:
    # ARRANGE
    service.answer_jsonrpc(RESULTS)
    handle = AsyncRemoteHandle(_settings(service), api=generated.async_jsonrpc.SampleApi)
    handle.api.get_balance.set_validation_mask({"amount": True})
    recorder = MaskRecorder()

    # ACT
    async with handle.batch() as batch:
        batch.api.callbacks.process_response.append(recorder)
        batch.api.get_head_block.set_validation_mask({"block_num": True})  # for the batch only
        await batch.api.get_balance(account_name="alice")
        await batch.api.get_head_block()

    # ASSERT
    assert recorder.seen == [{BALANCE: {"amount": True}, HEAD_BLOCK: {"block_num": True}}]
    assert handle.api.get_head_block.validation_mask is None, "masks set in a batch are not given back to its handle"


def test_masks_are_copied_between_collections_of_apis(generated: GeneratedClients, service: FakeService) -> None:
    # ARRANGE
    compiling_api = _compiling(generated.sync_jsonrpc.SampleApi)

    class Collection(AbstractSyncApiCollection):
        def __init__(self, owner: SyncSendable) -> None:
            super().__init__(owner)
            self.sample_api = compiling_api(owner)

    source = SyncRemoteHandle(_settings(service), api=Collection)
    target = SyncRemoteHandle(_settings(service), api=Collection)
    source.api.sample_api.get_balance.set_validation_mask({"amount": True})

    # ACT
    copy_validation_masks(source.api, target.api)

    # ASSERT - compiled by the API of the target
    endpoint = target.api.sample_api.get_balance
    assert (endpoint.validation_mask, endpoint.compiled_validation_mask) == (
        {"amount": True},
        ("compiled", "get_balance", ("amount",)),
    )
    assert target.api.sample_api.get_head_block.validation_mask is None


def test_batch_of_synchronous_handle_gives_masks_of_its_calls(
    generated: GeneratedClients, service: FakeService
) -> None:
    # ARRANGE
    service.answer_jsonrpc(RESULTS)
    handle = SyncRemoteHandle(_settings(service), api=generated.sync_jsonrpc.SampleApi)
    recorder = MaskRecorder()

    # ACT
    with handle.batch() as batch:
        batch.api.get_head_block.set_validation_mask({"block_num": True})
        batch.api.callbacks.process_response.append(recorder)
        batch.api.get_balance(account_name="alice")
        batch.api.get_head_block()

    # ASSERT
    assert recorder.seen == [{BALANCE: None, HEAD_BLOCK: {"block_num": True}}]
