from __future__ import annotations

import re
from typing import Any, Final


LIST_CLASS_NAME: Final[str] = "<class 'list'>"


def is_param_array(param: Any) -> bool:
    """
    Check is param array by converting it to the string and  checking presence of the `list` word.

    Check is performed this way, as it works with aliased types like `list[str]`, `some_alias = list[str]` as well.
    """

    return "list" in str(param)


def get_array_ready_for_annotation(param: Any) -> str:
    """
    Get array ready for annotation by converting it to the string and removing everything between the first `[` and the first `.` after it, inclusive.

    Examples:
        MyCustomAlias = list[str | int]


        class SomeClass:
            ...

        MySecondAlias = list[SomeClass]

        get_array_ready_for_annotation(MyCustomAlias)
        >>> "list[str | int]"

        get_array_ready_for_annotation(MySecondAlias)
        >>> "list[SomeAttribute]"
    """
    stringified = str(param)

    if stringified == LIST_CLASS_NAME:  # Empty list case, should be annotated as list[str]
        return "list[str]"

    return cut_from_bracket_to_dot(str(param))


def cut_from_bracket_to_dot(list_as_str: str) -> str:
    """Replace fully-qualified names inside [...] with just the last identifier."""

    def replacer(match):
        content = match.group(1)
        return "[" + content.split(".")[-1] + "]"

    return re.sub(r"\[([^\]]+)\]", replacer, list_as_str)


def extract_module_path(list_as_str: str) -> str:
    """
    Extract everything before the last '.' in a dotted path string.

    Example:
        extract_module_path("some_api.some_api_description.CondenserBroadcastTransactionItem")
        >>> "some_api.some_api_description"
    """
    if "." not in list_as_str:
        return ""

    splitted = ".".join(list_as_str.split(".")[:-1])

    if splitted.startswith("list["):
        splitted = splitted.replace("list[", "")

    if "<class '" in splitted:
        splitted = splitted.replace("<class '", "")

    return splitted


def extract_inner_type(list_as_str: str) -> str | None:
    """
    Extract the content inside the first [...] pair.

    Example:
        extract_inner_type("list[some_type]") -> "some_type"
    """
    match = re.search(r"\[([^\]]+)\]", list_as_str)
    return match.group(1) if match else None
