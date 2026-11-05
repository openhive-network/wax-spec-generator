from __future__ import annotations

import importlib
import json
import sys
import threading
import time
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import ModuleType
from typing import Any, Final

import pytest

from hiveio_api_client import AbstractAsyncApi, AbstractSyncApi, HttpUrl

_SAMPLES: Final[Path] = Path(__file__).parent
_PACKAGE: Final[str] = "generated_sample_clients"


@dataclass(frozen=True)
class GeneratedClients:
    """Modules of clients generated from the sample definitions, with the base classes of the runtime package."""

    async_rest: ModuleType
    sync_rest: ModuleType
    async_jsonrpc: ModuleType
    sync_jsonrpc: ModuleType


@pytest.fixture(scope="session")
def generated(tmp_path_factory: pytest.TempPathFactory) -> Iterator[GeneratedClients]:
    from api_client_generator.json_rpc import generate_api_client, generate_api_description
    from api_client_generator.rest import generate_api_client_from_swagger

    root = tmp_path_factory.mktemp("generated")
    package = root / _PACKAGE
    package.mkdir()
    (package / "__init__.py").touch()
    sys.path.insert(0, str(root))

    for name, base_class in (("async_rest", AbstractAsyncApi), ("sync_rest", AbstractSyncApi)):
        generate_api_client_from_swagger(
            _SAMPLES / "sample_rest_openapi.json",
            package / name,
            base_class,
            asynchronous=base_class is AbstractAsyncApi,
        )

    generate_api_description(
        "sample_api_description", _SAMPLES / "sample_jsonrpc_openapi.json", package / "description.py"
    )
    description_module = importlib.import_module(f"{_PACKAGE}.description")
    for name, base_class in (("async_jsonrpc", AbstractAsyncApi), ("sync_jsonrpc", AbstractSyncApi)):
        generate_api_client(
            description_module.sample_api_description,
            base_class,
            path=package / f"{name}.py",
            asynchronous=base_class is AbstractAsyncApi,
            description_module=description_module,
        )

    yield GeneratedClients(
        async_rest=importlib.import_module(f"{_PACKAGE}.async_rest.sample_api_client"),
        sync_rest=importlib.import_module(f"{_PACKAGE}.sync_rest.sample_api_client"),
        async_jsonrpc=importlib.import_module(f"{_PACKAGE}.async_jsonrpc"),
        sync_jsonrpc=importlib.import_module(f"{_PACKAGE}.sync_jsonrpc"),
    )
    sys.path.remove(str(root))


@dataclass(frozen=True)
class ReceivedRequest:
    method: str
    path: str
    headers: dict[str, str]
    body: str

    @property
    def json(self) -> Any:
        return json.loads(self.body)


Reply = tuple[int, str]


@dataclass
class FakeService:
    """HTTP service of tests - answers requests with `reply` (status and body), after `delay` seconds."""

    url: HttpUrl
    reply: Callable[[ReceivedRequest], Reply] = lambda _: (200, "{}")
    delay: float = 0
    requests: list[ReceivedRequest] = field(default_factory=list)

    def answer_jsonrpc(self, results: Mapping[str, object], errors: Mapping[str, object] | None = None) -> None:
        """Answer JSON-RPC calls (single ones and batches) with results or errors of their methods."""

        def answer(call: dict[str, Any]) -> dict[str, object]:
            envelope: dict[str, object] = {"jsonrpc": "2.0", "id": call["id"]}
            if errors is not None and call["method"] in errors:
                return envelope | {"error": errors[call["method"]]}
            return envelope | {"result": results[call["method"]]}

        def reply(request: ReceivedRequest) -> Reply:
            payload = request.json
            answered = [answer(call) for call in payload] if isinstance(payload, list) else answer(payload)
            return 200, json.dumps(answered)

        self.reply = reply


@pytest.fixture
def service() -> Iterator[FakeService]:
    fake: FakeService

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            self._answer()

        def do_POST(self) -> None:
            self._answer()

        def _answer(self) -> None:
            length = int(self.headers.get("Content-Length", 0))
            request = ReceivedRequest(
                method=self.command,
                path=self.path,
                headers=dict(self.headers.items()),
                body=self.rfile.read(length).decode(),
            )
            fake.requests.append(request)
            time.sleep(fake.delay)
            status, body = fake.reply(request)
            encoded = body.encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def log_message(self, format: str, *args: object) -> None:  # requests are not logged by tests
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    server.block_on_close = False
    fake = FakeService(url=HttpUrl(f"http://127.0.0.1:{server.server_address[1]}"))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield fake
    server.shutdown()
    server.server_close()
    thread.join()
