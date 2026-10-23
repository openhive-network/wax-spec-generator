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
import tempfile
from collections.abc import Container
from pathlib import Path
from typing import TYPE_CHECKING

from api_client_generator._private.common.converters import snake_to_camel
from api_client_generator._private.common.models_aliased import (
    ApiDescriptionBeforeProcessing,
    EndpointDescriptionBeforeProcessing,
)
from api_client_generator._private.description_tools import (
    AliasToAssign,
    create_api_description_module,
    get_description_for_endpoint,
    get_last_part_of_ref,
    get_params_name_for_endpoint,
    get_result_name_for_endpoint,
    is_result_array,
)
from api_client_generator._private.export_client_module_to_file import export_module_to_file
from api_client_generator.generate_types_from_swagger import (
    check_references,
    generate_types_from_swagger,
)
from api_client_generator.json_rpc.clean_openapi import clean_file
from api_client_generator.json_rpc.shared_models import share_models
from api_client_generator.model_options import CustomTypes, ModelOptions
from api_client_generator.openapi_flattening import flatten_openapi_file

if TYPE_CHECKING:
    from collections.abc import Mapping


def generate_api_description(
    api_description_name: str,
    openapi_api_definition: str | Path,
    output_file: str | Path,
    additional_aliases: tuple[AliasToAssign] | None = None,
    apis_to_skip: Container[str] | None = None,
    allow_passing_item_suffix: bool = True,
    *,
    model_options: ModelOptions | None = None,
    custom_types: CustomTypes | None = None,
    flatten: bool = False,
    deduplicate_models: bool = False,
) -> None:
    """
    Generate an API description based on the provided OpenAPI definition.

    Args:
        api_description_name: The name of the API description to be generated.
        openapi_api_definition: The OpenAPI JSON definition file path.
        output_file: The file where the generated API description will be saved.
        additional_aliases: Additional aliases to be used in the API description.
        apis_to_skip: APIs to skip during the generation process.
        allow_passing_item_suffix: Whether to allow passing the "Item" suffix for array response types.
        model_options: Shape of the generated models (msgspec struct / dataclass, base class, frozen, kw_only).
                       Defaults to plain msgspec structs.
        custom_types: Custom types replacing OpenAPI types of annotated schema nodes (vendor extension / format).
        flatten: Generate the types from the definition flattened by `api_client_generator.openapi_flattening`.
        deduplicate_models: With `flatten` - object schemas equal in structure become single components of the
                 flattened definition, so one model is generated for them (`api_client_generator.openapi_deduplication`).

    Raises:
        FileNotFoundError: If the OpenAPI definition file does not exist.
        UndefinedModelError: If the generated description refers to a model which is not generated.
    """
    openapi_api_definition = Path(openapi_api_definition)
    output_file = Path(output_file)
    if flatten:
        with tempfile.TemporaryDirectory() as directory:
            flattened_file = _flatten(
                openapi_api_definition,
                Path(directory),
                deduplicate_models=deduplicate_models,
                custom_types=custom_types,
            )
            generate_types_from_swagger(
                flattened_file, output_file, model_options=model_options, custom_types=custom_types
            )
    else:
        generate_types_from_swagger(
            openapi_api_definition, output_file, model_options=model_options, custom_types=custom_types
        )

    api_description = {
        api_name: endpoints
        for api_name, endpoints in _describe_apis(openapi_api_definition, allow_passing_item_suffix).items()
        if not apis_to_skip or api_name not in apis_to_skip
    }
    # only valid python identifiers can name the variable of the description dict
    _append_description(output_file, api_description_name.replace("-", "_"), api_description, additional_aliases)
    check_references(output_file)


def generate_api_descriptions(
    openapi_api_definition: str | Path,
    description_files: Mapping[str, Path],
    common_package: Path,
    common_import: str,
    *,
    allow_passing_item_suffix: bool = True,
    model_options: ModelOptions | None = None,
    custom_types: CustomTypes | None = None,
) -> dict[str, str]:
    """
    Generate descriptions of several APIs of the OpenAPI definition - models used by several APIs are shared.

    Models of all APIs are generated once, from the flattened and deduplicated definition (see `flatten` and
    `deduplicate_models` of `generate_api_description`), and divided between modules:

    - the description module of an API holds the models and type aliases used by its endpoints (directly or by other
      models) and the description of its endpoints (`<api>_description`, see `generate_api_description`),
    - models used by several APIs are moved to the common package (see `json_rpc.shared_models`) - description modules
      keep them as aliases, so every API offers all its models.

    Args:
        openapi_api_definition: The OpenAPI JSON definition file path.
        description_files: Description modules to generate by names of the APIs (prefixes of paths of the definition).
        common_package: Directory of the package of the shared models - its `__init__.py` is left to the caller.
        common_import: Import path of the common package (e.g. `my_package.common`).
        allow_passing_item_suffix: Whether to allow passing the "Item" suffix for array response types.
        model_options: Shape of the generated models (msgspec struct / dataclass, base class, frozen, kw_only).
                       Defaults to plain msgspec structs.
        custom_types: Custom types replacing OpenAPI types of annotated schema nodes (vendor extension / format).

    Returns:
        Modules of the common package (names in the package) by names of the shared models.

    Raises:
        FileNotFoundError: If the OpenAPI definition file does not exist.
        ValueError: If the definition has no endpoints of one of the APIs.
        UndefinedModelError: If a generated module refers to a model which is not generated.
    """
    openapi_api_definition = Path(openapi_api_definition)
    descriptions = _describe_apis(openapi_api_definition, allow_passing_item_suffix)
    if missing := [api for api in description_files if api not in descriptions]:
        raise ValueError(f"The definition has no endpoints of {', '.join(f'`{api}`' for api in missing)}.")

    with tempfile.TemporaryDirectory() as directory:
        flattened_file = _flatten(
            openapi_api_definition, Path(directory), deduplicate_models=True, custom_types=custom_types
        )
        models_file = Path(directory) / "models.py"
        generate_types_from_swagger(flattened_file, models_file, model_options=model_options, custom_types=custom_types)
        models = models_file.read_text()

    for api, description_file in description_files.items():
        description_file.parent.mkdir(parents=True, exist_ok=True)
        description_file.write_text(models)
        _append_description(description_file, f"{api}_description", {api: descriptions[api]})

    shared = share_models(models, description_files.values(), common_package, common_import)
    for module in [*description_files.values(), *(common_package / f"{name}.py" for name in shared.values())]:
        check_references(module)
    return shared


def _flatten(
    openapi_api_definition: Path, directory: Path, *, deduplicate_models: bool, custom_types: CustomTypes | None
) -> Path:
    """The flattened definition, written to the directory (named as generated modules mention it in their header)."""
    flattened_file = directory / "openapi_flattened.json"
    flatten_openapi_file(
        openapi_api_definition,
        flattened_file,
        deduplicate=deduplicate_models,
        custom_type_extension=custom_types.extension if custom_types is not None else None,
    )
    return flattened_file


def _describe_apis(openapi_api_definition: Path, allow_passing_item_suffix: bool) -> ApiDescriptionBeforeProcessing:
    """Descriptions of endpoints of all APIs of the definition, in the order of paths."""
    api_description: ApiDescriptionBeforeProcessing = {}

    openapi = json.loads(openapi_api_definition.read_text())

    paths = list(openapi["paths"].keys())  # path is construct like name_of_api.name_of_endpoint
    components = openapi["components"]["schemas"]

    for path in paths:
        api_name, endpoint_name = path.split(".")

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
            assert isinstance(endpoint_description["result"], str), "Result must be a string at this point."

            # `response_array` marks that `result` describes a single ELEMENT of the returned array. Without an item
            # model (no $ref, no "Item" suffix) `result` is the whole array type and must not be wrapped again.
            potential_ref = components[result_name].get("items", {}).get("$ref")
            if potential_ref:  # This means that the elements of the array are represented by a custom class/model/components, which are contained in the components section.
                endpoint_description["response_array"] = True
                endpoint_description["result"] = snake_to_camel(
                    get_last_part_of_ref(components[result_name]["items"]["$ref"])
                )
            elif allow_passing_item_suffix:
                endpoint_description["response_array"] = True
                endpoint_description["result"] += "Item"

        api_description[api_name][endpoint_name] = endpoint_description

    return api_description


def _append_description(
    module: Path,
    api_description_name: str,
    api_description: ApiDescriptionBeforeProcessing,
    additional_aliases: tuple[AliasToAssign] | None = None,
) -> None:
    """Remove models not used by the described endpoints from the generated module and append the description."""
    used_models: set[str] = set()
    for api in api_description.values():
        for endpoint in api.values():
            params = endpoint.get("params")
            result = endpoint.get("result")
            if isinstance(params, str) and params != "None":
                used_models.add(params)
            if isinstance(result, str) and result:
                used_models.add(result)

    clean_file(module, used_models)
    export_module_to_file(
        create_api_description_module(api_description_name, api_description, additional_aliases),
        mode="a",
        file_path=module,
    )
