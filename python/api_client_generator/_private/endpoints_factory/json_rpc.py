from __future__ import annotations

import ast
from typing import Any

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
                annotation=ast.Name(id=param.type.__name__),
            )
        )

    if legacy_args_serialization:
        arguments.posonlyargs = endpoints_args
        arguments.defaults = defaults  # type: ignore[assignment]
        return arguments

    arguments.kwonlyargs = endpoints_args
    arguments.kw_defaults = defaults
    return arguments
