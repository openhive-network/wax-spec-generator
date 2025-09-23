"""
Simple way to generate a JSON-RPC params-result structure to be used in the client generator.

This script reads the OpenAPI JSON file, generates the API description, and creates a dictionary like that:

api_description = {
    "name_of_api":
        {
        "name_of_endpoint": {

                "params": ParamsClass,
                "result": NameOfEndpointResponse,
                "description": "Description of the endpoint if given",
            },
        },
        "name_of_second_endpoint":
            {
                "name_of_endpoint": {
                    "params": ParamsClass,
                    "result": NameOfEndpointResponseItem,
                    "response_array": True,
                    "description": "Description of the endpoint if given",
                },
            },
        }
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Container

from api_client_generator._private.common.converters import snake_to_camel
from api_client_generator._private.common.models_aliased import (
    ApiDescriptionBeforeProcessing,
    EndpointDescriptionBeforeProcessing,
)
from api_client_generator._private.description_tools import (
    AliasToAssign,
    create_api_description_module,
    get_description_for_endpoint,
    get_params_name_for_endpoint,
    get_result_name_for_endpoint,
    is_result_array,
    get_last_part_of_ref,
)
from api_client_generator._private.export_client_module_to_file import export_module_to_file
from api_client_generator.generate_types_from_swagger import generate_types_from_swagger
from api_client_generator.json_rpc.clean_openapi import clean_file


def generate_api_description(
    api_description_name: str,
    openapi_api_definition: str | Path,
    output_file: str | Path,
    openapi_flattened_definition: str | Path | None = None,
    additional_aliases: tuple[AliasToAssign] | None = None,
    apis_to_skip: Container[str] | None = None,
    allow_passing_item_suffix: bool = True,
) -> None:
    """
    Generate an API description based on the provided OpenAPI definition.

    Args:
        api_description_name: The name of the API description to be generated.
        openapi_api_definition: The OpenAPI JSON definition file path.
        output_file: The file where the generated API description will be saved.
        openapi_flattened_definition: The flattened OpenAPI JSON definition file path. If provided, it will be used to
                                      generate the types instead of the original definition.
        additional_aliases: Additional aliases to be used in the API description.
        apis_to_skip: APIs to skip during the generation process.
        allow_passing_item_suffix: Whether to allow passing the "Item" suffix for array response types.

    Raises:
        FileNotFoundError: If the OpenAPI definition file does not exist.
    """
    openapi_api_definition = (
        openapi_api_definition if isinstance(openapi_api_definition, Path) else Path(openapi_api_definition)
    )
    openapi_flattened_definition = Path(openapi_flattened_definition) if openapi_flattened_definition else None
    output_file = output_file if isinstance(output_file, Path) else Path(output_file)
    generate_types_from_swagger(
        openapi_flattened_definition if openapi_flattened_definition is not None else openapi_api_definition,
        output_file,
    )

    api_description: ApiDescriptionBeforeProcessing = {}

    openapi = json.loads(openapi_api_definition.read_text())

    paths = list(openapi["paths"].keys())  # path is construct like name_of_api.name_of_endpoint
    components = openapi["components"]["schemas"]

    for path in paths:
        api_name, endpoint_name = path.split(".")

        if apis_to_skip and api_name in apis_to_skip:
            continue

        if api_name not in api_description:
            api_description[api_name] = {}

        endpoint_properties = openapi["paths"][path]

        params_name = get_params_name_for_endpoint(endpoint_properties)
        result_name = get_result_name_for_endpoint(
            endpoint_properties
        )  # that's the name of the response class, in the snake case

        endpoint_description: EndpointDescriptionBeforeProcessing = {
            "params": snake_to_camel(params_name) if params_name else "None",
            "result": snake_to_camel(result_name),
            "description": get_description_for_endpoint(endpoint_properties),
        }

        if is_result_array(result_name, components):
            endpoint_description["response_array"] = True

            assert isinstance(endpoint_description["result"], str), "Result must be a string at this point."

            potential_ref = components[result_name].get("items", {}).get("$ref")
            if potential_ref:  # This means that the elements of the array are represented by a custom class/model/components, which are contained in the components section.
                endpoint_description["result"] = snake_to_camel(
                    get_last_part_of_ref(components[result_name]["items"]["$ref"])
                )
            elif allow_passing_item_suffix:
                endpoint_description["result"] += "Item"

        api_description[api_name][endpoint_name] = endpoint_description

    if "-" in api_description_name:
        api_description_name = api_description_name.replace(
            "-", "_"
        )  # at this point, we want only valid python identifiers to assign the description dict to properly named variable

    description_module = create_api_description_module(api_description_name, api_description, additional_aliases)
    used_models: set[str] = set()

    for api in api_description.values():
        for endpoint in api.values():
            params = endpoint.get("params")
            result = endpoint.get("result")
            if params and params != "None":
                used_models.add(params)  # type: ignore
            if result:
                used_models.add(result)  # type: ignore

    clean_file(output_file, used_models)

    export_module_to_file(
        description_module,
        mode="a",
        file_path=output_file,
    )
