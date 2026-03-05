from __future__ import annotations

import ast

from api_client_generator._private.common.models_aliased import Importable


def _format_generic_list(result_type: Importable) -> str:
    """Format a generic list type (e.g. list[str]) as a string for AST annotation.

    Handles typing module types like Any that str() renders as 'typing.Any'.
    """
    args = getattr(result_type, "__args__", None)
    if args:
        arg_name = args[0].__name__ if hasattr(args[0], "__name__") else str(args[0])
        return f"list[{arg_name}]"
    return "list"


def create_endpoint(  # NOQA: PLR0913
    name: str,
    endpoint_arguments: ast.arguments,
    endpoint_decorator: str,
    result_type: Importable | str | None = None,
    description: str | None = None,
    *,
    response_array: bool = False,
    asynchronous: bool = True,
) -> ast.AsyncFunctionDef | ast.FunctionDef:
    """
    Create endpoint method.

    Args:
        name: The name of the endpoint.
        endpoint_arguments: The arguments for the endpoint.
        endpoint_decorator: The name of the endpoint decorator to be used.
        result_type: The type of the result.
        description: The description of the endpoint.
        response_array: If True, the result type will be a list of the result type.
        asynchronous: If True, the endpoint will be created as an asynchronous method.

    Notes:
        - The method body contains an ellipsis (`...`), decorator do all the work.
        - If `result_type` is provided, it will be used as the return type hint.
        - The first argument is always `self` (function always add it automatically).

    Returns:
        ast.AsyncFunctionDef | ast.FunctionDef: The AST representation of the endpoint method.
    """
    self_arg = ast.arg(arg="self")
    endpoint_arguments.posonlyargs.insert(
        0, self_arg
    ) if endpoint_arguments.posonlyargs else endpoint_arguments.args.insert(0, self_arg)
    body: list[ast.stmt] = [
        ast.Expr(value=ast.Constant(value=Ellipsis))
        if not description
        else ast.Expr(value=ast.Constant(value=description))
    ]

    returns: ast.Name | None

    if isinstance(result_type, str):
        returns = ast.Name(id=result_type)
    elif result_type is not None:
        if not response_array:
            returns = ast.Name(id=result_type.__name__)
        elif hasattr(result_type, "__origin__") and result_type.__origin__ is list:
            # Already a generic list type (e.g. list[str]) — use as-is, don't double-wrap
            returns = ast.Name(id=_format_generic_list(result_type))
        else:
            returns = ast.Name(id=f"list[{result_type.__name__}]")
    else:
        returns = None

    function_def: type[ast.FunctionDef] | type[ast.AsyncFunctionDef] = (
        ast.AsyncFunctionDef if asynchronous else ast.FunctionDef
    )

    return function_def(
        name=name,
        args=endpoint_arguments,
        body=body,
        decorator_list=[ast.Name(id=endpoint_decorator)],
        returns=returns,
        type_params=[],
    )
