from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING

from api_client_generator._private.common.converters import camel_to_snake, hyphen_to_snake
from api_client_generator._private.rest_api_tools.models_aliased import RestApiMethodType
from api_client_generator.exceptions import MethodNameCollisionError

if TYPE_CHECKING:
    from collections.abc import Iterable

Operation = tuple[str, RestApiMethodType]
"""URL path and HTTP method of an endpoint, e.g. ("/posts/{author}", "get")."""

_BARE_NAME_METHOD: RestApiMethodType = "get"


def _create_bare_method_name(url_path: str) -> str:
    """
    Create a method name for a REST API client based on the URL path.

    Args:
        url_path: The URL path of the endpoint, e.g., "/name_of_endpoint/{some_param}".

    Returns:
        url_path: The constructed method name.

    Example:
        my_url_path = "/name_of_endpoint/{some_param}/path_part"
        _create_bare_method_name(my_url_path)
        >>> "name_of_endpoint_path_part"
    """
    split_path = url_path.split("/")
    split_path = [part for part in split_path if part and not part.startswith("{") and not part.endswith("}")]

    return "_".join(split_path).replace("-", "_")


def _path_params(url_path: str) -> list[str]:
    return [
        camel_to_snake(hyphen_to_snake(part[1:-1]))
        for part in url_path.split("/")
        if part.startswith("{") and part.endswith("}")
    ]


def _create_path_names(url_paths: Iterable[str]) -> dict[str, str]:
    paths_by_bare_name: defaultdict[str, list[str]] = defaultdict(list)
    for url_path in url_paths:
        paths_by_bare_name[_create_bare_method_name(url_path)].append(url_path)

    names: dict[str, str] = {}
    for bare_name, colliding_paths in paths_by_bare_name.items():
        fewest_params = min(len(_path_params(url_path)) for url_path in colliding_paths)
        with_fewest_params = [url_path for url_path in colliding_paths if len(_path_params(url_path)) == fewest_params]
        for url_path in colliding_paths:
            params = _path_params(url_path)
            keeps_bare_name = with_fewest_params == [url_path] or not params
            names[url_path] = bare_name if keeps_bare_name else f"{bare_name}_by_{'_'.join(params)}"
    return names


def create_method_names(operations: Iterable[Operation]) -> dict[Operation, str]:
    """
    Create unique method names for all operations of a REST API.

    An operation keeps the name derived from its URL path (path parameters dropped) when it is unique. Among paths
    sharing that name the one with the fewest path parameters keeps it and the others get `_by_<param>[_<param>...]`.
    Among several HTTP methods of one path `get` keeps the name and the others get `_<method>`.

    Args:
        operations: URL paths and HTTP methods of all endpoints of the API.

    Returns:
        Method name of each operation.

    Raises:
        MethodNameCollisionError: If two operations still get the same name.
    """
    methods_by_path: defaultdict[str, list[RestApiMethodType]] = defaultdict(list)
    for url_path, method_type in operations:
        methods_by_path[url_path].append(method_type)

    path_names = _create_path_names(methods_by_path)

    names: dict[Operation, str] = {}
    operations_by_name: defaultdict[str, list[Operation]] = defaultdict(list)
    for url_path, method_types in methods_by_path.items():
        for method_type in method_types:
            name = path_names[url_path]
            if len(method_types) > 1 and method_type != _BARE_NAME_METHOD:
                name += f"_{method_type}"
            names[(url_path, method_type)] = name
            operations_by_name[name].append((url_path, method_type))

    collisions = {name: colliding for name, colliding in operations_by_name.items() if len(colliding) > 1}
    if collisions:
        raise MethodNameCollisionError(collisions)
    return names
