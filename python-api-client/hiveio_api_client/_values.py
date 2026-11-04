"""
Values of API calls - parameters converted to builtins and results built from parsed JSON.

How values are converted is given by the installed `ValueCodec`. The default one handles builtins, msgspec structs,
dataclasses and everything else `msgspec` converts. A library with its own field types (e.g. hiveio-api with Hive
assets and validating types) installs its codec with `install_value_codec` when it is imported.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol, TypeVar

import msgspec

__all__ = [
    "ValueBuilderFactory",
    "ValueCodec",
    "install_value_codec",
    "installed_value_codec",
    "json_default",
    "to_api_builtins",
    "value_builder",
]

T = TypeVar("T")


class ValueBuilderFactory(Protocol):
    """Returns a function building a value of the given type from parsed JSON - see `ValueCodec.value_builder`."""

    def __call__(self, annotation: type[T], /) -> Callable[[object], T]: ...


def _msgspec_to_api_builtins(value: object, testnet: Callable[[], bool]) -> object:  # builtins of any network
    return msgspec.to_builtins(value)


def _msgspec_value_builder(annotation: type[T]) -> Callable[[object], T]:
    def build(value: object) -> T:
        try:
            built: T = msgspec.convert(value, annotation, strict=False)
        except msgspec.ValidationError as error:
            raise ValueError(str(error)) from error
        return built

    return build


def _not_serializable(value: object) -> object:
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


@dataclass(frozen=True, kw_only=True)
class ValueCodec:
    """
    Conversion of values of API calls - the extension point for libraries with their own field types.

    Attributes:
        to_api_builtins: Converts parameters of a call to builtins `json` serializes - called with the parameters and
            a callable telling whether the receiver is a testnet (asked only when the conversion depends on it).
            Values it leaves unconverted are given to `json_default`.
        value_builder: Returns a function building a value of the given type from parsed JSON (results of calls). The
            function raises `ValueError` when the value does not match the type.
        json_default: `default` of `json.dumps` - builtins of values `json` can not serialize, `TypeError` otherwise.
    """

    to_api_builtins: Callable[[object, Callable[[], bool]], object] = _msgspec_to_api_builtins
    value_builder: ValueBuilderFactory = _msgspec_value_builder
    json_default: Callable[[object], object] = _not_serializable


_installed_codec: ValueCodec = ValueCodec()


def install_value_codec(codec: ValueCodec) -> ValueCodec:
    """
    Use the codec for values of all API calls of the process, from now on.

    Returns:
        The codec installed before - to restore it (e.g. in tests).
    """
    global _installed_codec  # the codec is process-wide by design
    previous = _installed_codec
    _installed_codec = codec
    return previous


def installed_value_codec() -> ValueCodec:
    """The codec used for values of API calls."""
    return _installed_codec


def to_api_builtins(value: object, *, testnet: Callable[[], bool]) -> object:
    """
    Convert parameters of an API call to builtins - by `to_api_builtins` of the installed codec.

    Args:
        value: Parameters - models and builtins, also nested in lists, tuples and dicts.
        testnet: Tells whether the receiver is a testnet - called only when the conversion depends on it.
    """
    return _installed_codec.to_api_builtins(value, testnet)


def value_builder(annotation: type[T]) -> Callable[[object], T]:
    """Return a function building a value of the given type from parsed JSON - by the installed codec."""
    return _installed_codec.value_builder(annotation)


def json_default(value: object) -> object:
    """`default` of `json.dumps` for parameters of API calls - by the installed codec."""
    return _installed_codec.json_default(value)
