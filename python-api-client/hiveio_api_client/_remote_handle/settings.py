from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta

from hiveio_api_client._communication.url import HttpUrl


@dataclass(kw_only=True)
class RemoteHandleSettings:
    """
    Settings of a remote handle - the service it calls, timeouts and retries of requests.

    Raises:
        ValueError: When `max_retries` is negative.
    """

    http_endpoint: HttpUrl
    """
    URL of the service. JSON-RPC calls are sent to it; REST calls to its protocol, address and port with the path of the
    endpoint.
    """

    timeout: timedelta = field(default_factory=lambda: timedelta(seconds=5))
    """Maximum time of a single attempt of a request."""

    max_retries: int = 5
    """How many times a request is sent again when no response was received (`CommunicationError`)."""

    period_between_retries: timedelta = field(default_factory=lambda: timedelta(seconds=0.2))
    """Period between a failed attempt and the next one."""

    def __post_init__(self) -> None:
        if self.max_retries < 0:
            raise ValueError(f"`max_retries` can not be negative, got: {self.max_retries}")
