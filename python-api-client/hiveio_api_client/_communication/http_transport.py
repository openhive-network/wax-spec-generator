"""
HTTP(S) transport of requests - the standard library (`urllib`), so the package needs no HTTP library.

Asynchronous handles send requests in a worker thread (`asyncio.to_thread`).
"""

from __future__ import annotations

import http.client
import urllib.error
import urllib.request

from hiveio_api_client._communication.abc.communicator_models import Request, Response
from hiveio_api_client.exceptions import CommunicationError, TimeoutExceededError

_ENCODING = "utf-8"


def send_http_request(request: Request) -> Response:
    """
    Send the request and return its response - also the one with an HTTP error status.

    Raises:
        TimeoutExceededError: The service did not answer within the timeout of the request.
        CommunicationError: Connecting to the service or sending the request failed.
    """
    http_request = urllib.request.Request(
        url=request.url.as_string(),
        data=None if request.body is None else request.body.encode(_ENCODING),
        headers=request.headers,
        method=request.method,
    )
    try:
        with urllib.request.urlopen(http_request, timeout=request.get_timeout()) as reply:
            return _response(reply.status, dict(reply.headers.items()), reply.read())
    except urllib.error.HTTPError as error:  # a response with an error status - judged by the handle
        with error:
            return _response(error.code, dict(error.headers.items()), error.read())
    except TimeoutError as error:
        raise TimeoutExceededError(request.url, request.body, request.get_timeout()) from error
    except urllib.error.URLError as error:
        if isinstance(error.reason, TimeoutError):
            raise TimeoutExceededError(request.url, request.body, request.get_timeout()) from error
        raise CommunicationError(request.url, request.body, str(error.reason)) from error
    except (OSError, http.client.HTTPException) as error:
        raise CommunicationError(request.url, request.body, repr(error)) from error


def _response(status: int, headers: dict[str, str], body: bytes) -> Response:
    return Response(status_code=status, headers=headers, body=body.decode(_ENCODING, errors="replace"))
