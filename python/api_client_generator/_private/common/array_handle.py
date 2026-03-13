from __future__ import annotations

import types
import typing as t
from typing import Any, Final


LIST_CLASS_NAME: Final[str] = "<class 'list'>"


def is_param_array(param: Any) -> bool:
    """Return True when parameter annotation represents a list."""

    origin = t.get_origin(param)
    if origin is not None:
        return origin is list

    if isinstance(param, list) or param is list:
        return True

    if str(param) == LIST_CLASS_NAME:
        return True

    if isinstance(param, str):
        stripped = param.strip()
        return stripped.startswith("list[") or stripped == "list"

    return False


def get_array_ready_for_annotation(param: Any) -> str:
    """Return a string representation suitable for annotating list parameters."""

    if isinstance(param, str):
        stripped = param.strip()
        if stripped.startswith("list["):
            return stripped
        return f"list[{stripped}]"

    if param is list or str(param) == LIST_CLASS_NAME:
        return "list[str]"

    origin = t.get_origin(param)
    if origin is list:
        args = t.get_args(param)
        if not args:
            return "list[str]"

        inner = format_annotation(args[0]) if len(args) == 1 else " | ".join(format_annotation(arg) for arg in args)
        return f"list[{inner}]"

    return "list[str]"


def format_annotation(annotation: Any) -> str:
    origin = t.get_origin(annotation)

    if origin is None:
        if isinstance(annotation, str):
            return annotation.split(".")[-1]

        if annotation is type(None):
            return "None"

        name = getattr(annotation, "__name__", None) or getattr(annotation, "_name", None)
        if name:
            return name

        return str(annotation).split(".")[-1]

    args = t.get_args(annotation)

    if origin is list:
        return f"list[{_format_collection_args(args)}]"

    if origin is tuple:
        if len(args) == 2 and args[1] is Ellipsis:
            return f"tuple[{format_annotation(args[0])}, ...]"
        return f"tuple[{', '.join(format_annotation(arg) for arg in args)}]"

    if origin is dict and len(args) == 2:
        key, value = args
        return f"dict[{format_annotation(key)}, {format_annotation(value)}]"

    if origin is set:
        return f"set[{_format_collection_args(args)}]"

    if origin in (t.Union, types.UnionType):
        return " | ".join(format_annotation(arg) for arg in args)

    origin_name = getattr(origin, "__name__", str(origin))
    formatted_args = ", ".join(format_annotation(arg) for arg in args)
    return f"{origin_name}[{formatted_args}]" if formatted_args else origin_name


def _format_collection_args(args: tuple[Any, ...]) -> str:
    if not args:
        return "str"

    if len(args) == 1:
        return format_annotation(args[0])

    return " | ".join(format_annotation(arg) for arg in args)
