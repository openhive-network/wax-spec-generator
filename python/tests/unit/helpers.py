from __future__ import annotations

import ast
import importlib.util
import json
import sys
from typing import TYPE_CHECKING

from api_client_generator.generate_types_from_swagger import generate_types_from_swagger
from api_client_generator.json_rpc import generate_api_description

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path
    from types import ModuleType

    import pytest

    from api_client_generator.model_options import CustomTypes, ModelOptions


def _content(schema: str) -> dict[str, object]:
    return {"content": {"application/json": {"schema": {"$ref": f"#/components/schemas/{schema}"}}}}


def definition(
    schemas: Mapping[str, object], endpoints: Mapping[str, tuple[str, str]] | None = None
) -> dict[str, object]:
    """OpenAPI definition of the schemas and of JSON-RPC endpoints (`api.method` -> params and result schemas)."""
    paths = {
        path: {"post": {"requestBody": _content(params), "responses": {"200": _content(result)}}}
        for path, (params, result) in (endpoints or {}).items()
    }
    return {
        "openapi": "3.1.0",
        "info": {"title": "test", "version": "1"},
        "paths": paths,
        "components": {"schemas": schemas},
    }


def schemas_of(openapi: dict[str, object]) -> dict[str, object]:
    components = openapi["components"]
    assert isinstance(components, dict)
    schemas = components["schemas"]
    assert isinstance(schemas, dict)
    return schemas


def write_definition(tmp_path: Path, openapi: dict[str, object]) -> Path:
    openapi_file = tmp_path / "openapi.json"
    openapi_file.write_text(json.dumps(openapi))
    return openapi_file


def generate_description(
    tmp_path: Path,
    openapi: dict[str, object],
    name: str = "description",
    *,
    allow_passing_item_suffix: bool = True,
    model_options: ModelOptions | None = None,
    custom_types: CustomTypes | None = None,
    flatten: bool = False,
    deduplicate_models: bool = False,
) -> Path:
    output = tmp_path / f"{name}.py"
    generate_api_description(
        "test_api_description",
        write_definition(tmp_path, openapi),
        output,
        allow_passing_item_suffix=allow_passing_item_suffix,
        model_options=model_options,
        custom_types=custom_types,
        flatten=flatten,
        deduplicate_models=deduplicate_models,
    )
    return output


def generate_models(
    tmp_path: Path, openapi: dict[str, object], model_options: ModelOptions, name: str = "models"
) -> Path:
    output = tmp_path / f"{name}.py"
    generate_types_from_swagger(write_definition(tmp_path, openapi), output, model_options=model_options)
    return output


def classes(source: str) -> dict[str, ast.ClassDef]:
    return {node.name: node for node in ast.parse(source).body if isinstance(node, ast.ClassDef)}


def field_assignment(class_node: ast.ClassDef, field_name: str) -> ast.AnnAssign:
    for statement in class_node.body:
        if isinstance(statement, ast.AnnAssign) and ast.unparse(statement.target) == field_name:
            return statement
    raise AssertionError(f"{field_name} not found")


def annotation(class_node: ast.ClassDef, field_name: str) -> str:
    return ast.unparse(field_assignment(class_node, field_name).annotation)


def import_module(path: Path, monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    module_name = f"generated_{path.parent.name}_{path.stem}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, module_name, module)  # type hints of models are resolved in their module
    spec.loader.exec_module(module)
    return module
