from __future__ import annotations

import ast
import types
from typing import Any, Union, get_args, get_origin

from msgspec import NODEFAULT, Struct
from msgspec.structs import fields

from api_client_generator._private.common.array_handle import is_param_array, get_array_ready_for_annotation
from api_client_generator._private.common.defaults import DEFAULT_ENDPOINT_JSON_RPC_DECORATOR_NAME
from api_client_generator._private.common.models_aliased import Importable
from api_client_generator._private.endpoints_factory.common import (
    create_endpoint as create_endpoint_common,
)
from api_client_generator._private.resolve_needed_imports import is_struct
from api_client_generator.exceptions import EndpointParamsIsNotMsgspecStructError


def _get_type_annotation_str(type_: Any) -> str:
    """
    Get a string representation of a type suitable for use in AST annotation.

    Handles union types (X | Y and Union[X, Y]), generic types, and regular types.
    """
    # Handle None type
    if type_ is type(None):  # noqa: E721
        return "None"

    # Handle union types (X | Y syntax or Union[X, Y])
    origin = get_origin(type_)
    if origin is Union or isinstance(type_, types.UnionType):
        args = get_args(type_)
        arg_strs = [_get_type_annotation_str(arg) for arg in args]
        return " | ".join(arg_strs)

    # Handle other generic types (list[str], dict[str, int], etc.)
    if origin is not None:
        args = get_args(type_)
        if args:
            arg_strs = [_get_type_annotation_str(arg) for arg in args]
            origin_name = origin.__name__ if hasattr(origin, "__name__") else str(origin)
            return f"{origin_name}[{', '.join(arg_strs)}]"
        return origin.__name__ if hasattr(origin, "__name__") else str(origin)

    # Regular type with __name__
    if hasattr(type_, "__name__"):
        return type_.__name__

    # Fallback to string representation
    return str(type_)


def create_endpoint(  # NOQA: PLR0913
    name: str,
    params: Struct | None = None,
    result: Importable | None = None,
    endpoint_decorator: str = DEFAULT_ENDPOINT_JSON_RPC_DECORATOR_NAME,
    description: str | None = None,
    *,
    response_array: bool = False,
    asynchronous: bool = True,
    legacy_args_serialization: bool = False,
) -> ast.AsyncFunctionDef | ast.FunctionDef:
    """
    Create JSON-RPC endpoint method.

    Args:
        name: The name of the endpoint.
        params: A msgspec struct of parameters.
        result: The type of the result.
        endpoint_decorator: The decorator for the endpoint.
        description: The description of the endpoint.
        response_array: If True, the result type will be a list of the result type.
        asynchronous: If True, the endpoint will be created as an asynchronous method.
        legacy_args_serialization: If True, endpoint arguments will be `posonlyargs`.

    Notice:
        Please note that the `params` argument is expected to be a msgspec struct.

    Returns:
        ast.AsyncFunctionDef | ast.FunctionDef: The AST representation of the endpoint method.

    Raises:
        EndpointParamsIsNotMsgspecStructError: If the params is not a msgspec struct.
    """

    return create_endpoint_common(
        name,
        get_endpoint_args(params, legacy_args_serialization=legacy_args_serialization),
        endpoint_decorator,
        result,
        description,
        response_array=response_array,
        asynchronous=asynchronous,
    )


def get_endpoint_args(params: Struct | list[Any] | None, *, legacy_args_serialization: bool = False) -> ast.arguments:
    """
    Generate arguments for the json-rpc api endpoint method.

    Args:
        params: The msgspec struct representing the parameters for the API endpoint.
        legacy_args_serialization: If True, endpoint arguments will be `posonlyargs`.

    Returns:
        ast.arguments: The arguments for the API endpoint method.

    Raises:
        EndpointParamsIsNotMsgspecStructError: If the params is not a msgspec struct.
    """

    arguments = ast.arguments(
        posonlyargs=[],
        args=[],
        kwonlyargs=[],
        kw_defaults=[],
        kwarg=None,
        defaults=[],
    )

    if params is None:
        return arguments

    endpoints_args: list[ast.arg] = []  # For legacy API's -> all posonlyargs, for new API's -> all kwonlyargs
    defaults: list[ast.expr | None] = []

    if is_param_array(params) or isinstance(params, list):  # Special case for array parameters -> legacy endpoints
        endpoints_args.append(
            ast.arg(
                arg="array_param",
                annotation=ast.Name(id=get_array_ready_for_annotation(params)),
            )
        )
        arguments.posonlyargs = endpoints_args
        return arguments

    if not is_struct(params):
        raise EndpointParamsIsNotMsgspecStructError

    for param in fields(params):
        if param.default is not NODEFAULT:
            defaults.append(ast.Constant(value=param.default))
        else:
            defaults.append(None)

        endpoints_args.append(
            ast.arg(
                arg=param.name,
                annotation=ast.Name(id=_get_type_annotation_str(param.type)),
            )
        )

    if legacy_args_serialization:
        arguments.posonlyargs = endpoints_args
        arguments.defaults = defaults  # type: ignore[assignment]
        return arguments

    arguments.kwonlyargs = endpoints_args
    arguments.kw_defaults = defaults
    return arguments
