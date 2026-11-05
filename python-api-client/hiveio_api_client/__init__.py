"""
Runtime of generated API clients - base classes of APIs and API collections, their owners (`SyncSendable`,
`AsyncSendable`), callbacks of requests, requests and responses, JSON-RPC, URLs and builtins of parameters of API calls
(`to_api_builtins`), with the extension point for libraries with their own field types (`ValueCodec`).

Handles of remote services (`SyncRemoteHandle`, `AsyncRemoteHandle`) send calls of the APIs over HTTP - single ones and
batches (`SyncBatchHandle`, `AsyncBatchHandle`); exceptions they raise are in `hiveio_api_client.exceptions`.

Names are imported from their modules when used for the first time.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from hiveio_api_client._utilities.smart_lazy_import import (
    aggregate_same_import,
    lazy_module_factory,
)

__version__ = "0.0.0"

if TYPE_CHECKING:
    from hiveio_api_client._apis.abc.api import (
        AbstractAsyncApi,
        AbstractSyncApi,
        ApiArgumentSerialization,
        ApiArgumentsToSerialize,
        HandleT,
        RegisteredApisT,
    )
    from hiveio_api_client._apis.abc.api_collection import (
        AbstractAsyncApiCollection,
        AbstractSyncApiCollection,
    )
    from hiveio_api_client._apis.abc.sendable import (
        AsyncSendable,
        SyncSendable,
    )
    from hiveio_api_client._communication.abc.communicator_models import (
        AsyncCallback,
        AsyncCallbacks,
        AsyncErrorCallback,
        AsyncRequestCallback,
        AsyncResponseCallback,
        Callbacks,
        ErrorCallback,
        Methods,
        Request,
        RequestCallback,
        RequestContext,
        RequestTimings,
        Response,
        ResponseCallback,
        SyncCallback,
    )
    from hiveio_api_client._communication.jsonrpc import (
        ExpectResultT,
        JSONRPCError,
        JSONRPCRequest,
        JSONRPCResult,
        build_response,
    )
    from hiveio_api_client._communication.url import (
        AnyUrl,
        HttpUrl,
        P2PUrl,
        Url,
        WsUrl,
    )
    from hiveio_api_client._remote_handle.batch_handle import (
        AsyncBatchHandle,
        SyncBatchHandle,
    )
    from hiveio_api_client._remote_handle.handle import (
        AsyncRemoteHandle,
        SyncRemoteHandle,
    )
    from hiveio_api_client._remote_handle.settings import RemoteHandleSettings
    from hiveio_api_client._values import (
        ValueBuilderFactory,
        ValueCodec,
        install_value_codec,
        installed_value_codec,
        to_api_builtins,
    )

__all__ = [
    "AbstractAsyncApi",
    "AbstractAsyncApiCollection",
    "AbstractSyncApi",
    "AbstractSyncApiCollection",
    "AnyUrl",
    "ApiArgumentSerialization",
    "ApiArgumentsToSerialize",
    "AsyncBatchHandle",
    "AsyncCallback",
    "AsyncCallbacks",
    "AsyncErrorCallback",
    "AsyncRemoteHandle",
    "AsyncRequestCallback",
    "AsyncResponseCallback",
    "AsyncSendable",
    "Callbacks",
    "ErrorCallback",
    "ExpectResultT",
    "HandleT",
    "HttpUrl",
    "JSONRPCError",
    "JSONRPCRequest",
    "JSONRPCResult",
    "Methods",
    "P2PUrl",
    "RegisteredApisT",
    "RemoteHandleSettings",
    "Request",
    "RequestCallback",
    "RequestContext",
    "RequestTimings",
    "Response",
    "ResponseCallback",
    "SyncBatchHandle",
    "SyncCallback",
    "SyncRemoteHandle",
    "SyncSendable",
    "Url",
    "ValueBuilderFactory",
    "ValueCodec",
    "WsUrl",
    "build_response",
    "install_value_codec",
    "installed_value_codec",
    "to_api_builtins",
]

__getattr__ = lazy_module_factory(
    globals(),
    *aggregate_same_import(
        "AbstractAsyncApi",
        "AbstractSyncApi",
        "ApiArgumentSerialization",
        "ApiArgumentsToSerialize",
        "HandleT",
        "RegisteredApisT",
        module="hiveio_api_client._apis.abc.api",
    ),
    *aggregate_same_import(
        "AbstractAsyncApiCollection",
        "AbstractSyncApiCollection",
        module="hiveio_api_client._apis.abc.api_collection",
    ),
    *aggregate_same_import(
        "AsyncSendable",
        "SyncSendable",
        module="hiveio_api_client._apis.abc.sendable",
    ),
    *aggregate_same_import(
        "AsyncCallback",
        "AsyncCallbacks",
        "AsyncErrorCallback",
        "AsyncRequestCallback",
        "AsyncResponseCallback",
        "Callbacks",
        "ErrorCallback",
        "Methods",
        "Request",
        "RequestCallback",
        "RequestContext",
        "RequestTimings",
        "Response",
        "ResponseCallback",
        "SyncCallback",
        module="hiveio_api_client._communication.abc.communicator_models",
    ),
    *aggregate_same_import(
        "ExpectResultT",
        "JSONRPCError",
        "JSONRPCRequest",
        "JSONRPCResult",
        "build_response",
        module="hiveio_api_client._communication.jsonrpc",
    ),
    *aggregate_same_import(
        "AnyUrl",
        "HttpUrl",
        "P2PUrl",
        "Url",
        "WsUrl",
        module="hiveio_api_client._communication.url",
    ),
    *aggregate_same_import(
        "AsyncBatchHandle",
        "SyncBatchHandle",
        module="hiveio_api_client._remote_handle.batch_handle",
    ),
    *aggregate_same_import(
        "AsyncRemoteHandle",
        "SyncRemoteHandle",
        module="hiveio_api_client._remote_handle.handle",
    ),
    ("hiveio_api_client._remote_handle.settings", "RemoteHandleSettings"),
    *aggregate_same_import(
        "ValueBuilderFactory",
        "ValueCodec",
        "install_value_codec",
        "installed_value_codec",
        "to_api_builtins",
        module="hiveio_api_client._values",
    ),
)
