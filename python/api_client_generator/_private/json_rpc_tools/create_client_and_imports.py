from __future__ import annotations

import typing as t
from typing import TYPE_CHECKING, Any, Sequence

from api_client_generator._private.common.array_handle import is_param_array
from api_client_generator._private.common.defaults import DEFAULT_ENDPOINT_JSON_RPC_DECORATOR_NAME
from api_client_generator._private.common.generated_class import GeneratedClass
from api_client_generator._private.common.models_aliased import (
    BaseApiClass,
    ClientClassFactory,
    EndpointsDescription,
    Importable,
    ensure_is_importable,
)
from api_client_generator._private.resolve_needed_imports import (
    import_class,
    import_classes,
    import_params_types,
    is_struct,
)
from api_client_generator.exceptions import EndpointParamsIsNotMsgspecStructError

if TYPE_CHECKING:
    import ast


def _iter_annotation_leaf_types(annotation: Any) -> t.Iterator[Any]:
    origin = t.get_origin(annotation)

    if origin is None:
        yield annotation
        return

    for arg in t.get_args(annotation):
        yield from _iter_annotation_leaf_types(arg)


def _import_annotation_type(annotation: Any, already_imported: list[str]) -> "ast.ImportFrom" | None:
    if isinstance(annotation, str):
        module_name, _, class_name = annotation.rpartition(".")

        if not class_name or not module_name or class_name in already_imported:
            return None

        import_stmt = import_class(class_name, module_name)
        if import_stmt:
            already_imported.append(class_name)
        return import_stmt

    if not hasattr(annotation, "__module__") or not hasattr(annotation, "__name__"):
        return None

    if annotation.__module__ == "builtins" or annotation.__name__ in already_imported:
        return None

    import_stmt = import_class(annotation)
    if import_stmt:
        already_imported.append(annotation.__name__)
    return import_stmt


def _collect_generic_type_imports(annotation: Any, already_imported: list[str]) -> list["ast.ImportFrom"]:
    imports: list["ast.ImportFrom"] = []

    for nested in _iter_annotation_leaf_types(annotation):
        import_stmt = _import_annotation_type(nested, already_imported)
        if import_stmt:
            imports.append(import_stmt)

    return imports


def create_client_and_imports(  # NOQA: PLR0913
    api_name: str,
    client_class_factory: ClientClassFactory,
    endpoints: EndpointsDescription,
    base_class: type[BaseApiClass] | str,
    base_class_source: str | None = None,
    endpoint_decorator: str = DEFAULT_ENDPOINT_JSON_RPC_DECORATOR_NAME,
    additional_items_to_import: Sequence[Importable] | None = None,
    already_imported: list[str] | None = None,
    *,
    asynchronous: bool = True,
    legacy_args_serialization: bool = False,
) -> GeneratedClass:
    """
    Create a client class and resolve the needed imports.

    Args:
        api_name: The name of the API.
        client_class_factory: The factory function to create the client class.
        endpoints: The endpoints description for the API.
        base_class: The base class for the API client.
        base_class_source: The source of the base class.
        endpoint_decorator: The name of the endpoint decorator to be used.
        additional_items_to_import: Additional items to import.
        already_imported: A list of already imported items.
        asynchronous: If True, the endpoints will be created as asynchronous methods.
        legacy_args_serialization: If True, endpoint arguments will be `posonlyargs`.

    Raises:
        EndpointParamsIsNotDataclassError: If the endpoint parameters are not a dataclass.
    """

    needed_imports: list[ast.ImportFrom] = []
    if already_imported is None:
        already_imported = []

    needed_results = [ensure_is_importable(params["result"]) for params in endpoints.values() if params.get("result")]
    needed_results_import = import_classes(needed_results, already_imported)

    needed_params_import = []

    for params in endpoints.values():
        if params.get("params") is not None:
            extracted_params = params.get("params")

            if is_param_array(extracted_params):
                needed_params_import.extend(_collect_generic_type_imports(extracted_params, already_imported))
                continue

            if extracted_params is not None and not is_struct(extracted_params):
                raise EndpointParamsIsNotMsgspecStructError

            needed_params_import.extend(import_params_types(extracted_params, already_imported))

    additional_imports = import_classes(additional_items_to_import or [], already_imported)

    needed_imports.extend(additional_imports + needed_results_import + needed_params_import)

    base_class_import = import_class(base_class, base_class_source)

    base_class_name = base_class if isinstance(base_class, str) else base_class.__name__

    if base_class_import and base_class_name not in already_imported:
        already_imported.append(base_class_name)
        needed_imports.append(base_class_import)

    return GeneratedClass(
        client_class_factory(
            api_name,
            endpoints,
            base_class,
            endpoint_decorator,
            asynchronous=asynchronous,
            legacy_args_serialization=legacy_args_serialization,
        ),
        needed_imports,
    )
