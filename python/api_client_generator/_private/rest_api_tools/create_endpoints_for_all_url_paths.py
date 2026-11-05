from __future__ import annotations

from typing import TYPE_CHECKING, Any

import msgspec

from api_client_generator._private.common.converters import snake_to_camel
from api_client_generator._private.common.models_aliased import SwaggerReadyForExtraction
from api_client_generator._private.common.openapi_to_python_type import convert_openapi_type_to_python_type
from api_client_generator._private.description_tools import (
    get_last_part_of_ref,
    get_value_from_swagger_part_recursively,
)
from api_client_generator._private.endpoints_factory.rest import create_endpoint
from api_client_generator._private.rest_api_tools.create_method_name import create_method_names
from api_client_generator._private.rest_api_tools.models_aliased import (
    CreatedEndpoints,
    RestApiMethodType,
    is_valid_rest_api_method_type,
)
from api_client_generator._private.rest_api_tools.rest_method_model import RestApiMethod
from api_client_generator.exceptions import UnsupportedHttpMethodError

if TYPE_CHECKING:
    import ast


def create_endpoints_for_all_url_paths(
    swagger: SwaggerReadyForExtraction, *, asynchronous: bool = True
) -> CreatedEndpoints:
    """
    Create endpoints for all URL paths defined in the Swagger/OpenAPI specification.

    Args:
        swagger: The Swagger/OpenAPI specification as a dictionary.
        asynchronous: If True, the endpoints will be created as asynchronous methods.

    Returns:
        A list of endpoints created from the Swagger paths.

    Raises:
        UnsupportedHttpMethodError: If a path defines an unsupported HTTP method.
        MethodNameCollisionError: If two operations cannot be given distinct method names.
    """

    paths_from_swagger = swagger["paths"]
    assert isinstance(paths_from_swagger, dict), f"Expected paths to be a dict, got {type(paths_from_swagger)}"

    url_paths = list(paths_from_swagger.keys())  # path is url like /name_of_endpoint/{some_param}
    endpoints: list[ast.FunctionDef | ast.AsyncFunctionDef] = []
    operations: list[tuple[str, dict[str, Any], RestApiMethodType]] = []

    for url_path in url_paths:
        path = get_value_from_swagger_part_recursively(swagger, ("paths", url_path))
        assert isinstance(path, dict), f"Expected path to be a dict, got {type(path)} for {url_path}"

        for method_type in path:  # e.g. ['get', 'post', 'put', 'delete']
            if not is_valid_rest_api_method_type(method_type):
                raise UnsupportedHttpMethodError(method_type)
            operations.append((url_path, path, method_type))

    method_names = create_method_names((url_path, method_type) for url_path, _, method_type in operations)

    for url_path, path, method_type in operations:
        method_name = method_names[(url_path, method_type)]
        response_schema = get_value_from_swagger_part_recursively(
            path, (method_type, "responses", "200", "content", "application/json", "schema")
        )
        response: str | type

        if "$ref" in response_schema:
            ref = response_schema["$ref"]
            response = snake_to_camel(get_last_part_of_ref(ref).split(".")[1])
        else:
            response = convert_openapi_type_to_python_type(response_schema["type"])

        method = msgspec.convert(path[method_type], RestApiMethod)

        endpoints.append(
            create_endpoint(method_name, url_path, method, response, method_type, asynchronous=asynchronous)
        )

    return endpoints
