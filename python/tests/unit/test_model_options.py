from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any

import pytest

from api_client_generator.exceptions import UnknownCustomTypeError
from api_client_generator.json_rpc import generate_api_description
from api_client_generator.model_options import CustomTypes, ModelOptions, is_model, model_fields

OPENAPI: dict[str, Any] = {
    "openapi": "3.1.0",
    "info": {"title": "test", "version": "1"},
    "paths": {
        "test_api.get_account": {
            "post": {
                "requestBody": {
                    "content": {"application/json": {"schema": {"$ref": "#/components/schemas/get_account"}}}
                },
                "responses": {
                    "200": {
                        "content": {
                            "application/json": {"schema": {"$ref": "#/components/schemas/get_account_response"}}
                        }
                    }
                },
            }
        },
        "test_api.get_names": {
            "post": {
                "requestBody": {
                    "content": {"application/json": {"schema": {"$ref": "#/components/schemas/get_account"}}}
                },
                "responses": {
                    "200": {
                        "content": {"application/json": {"schema": {"$ref": "#/components/schemas/get_names_response"}}}
                    }
                },
            }
        },
    },
    "components": {
        "schemas": {
            "big_int": {"x-test-type": "BigInt", "oneOf": [{"type": "string"}, {"type": "integer"}]},
            "get_account": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]},
            "get_account_response": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "x-test-type": "Name"},
                    "from": {"type": "string"},
                    "balance": {"$ref": "#/components/schemas/big_int"},
                    "created": {"type": "string", "format": "date-time"},
                    "id_or_object": {"oneOf": [{"type": "integer", "x-test-type": "Id"}, {"type": "object"}]},
                    "comment": {"type": "string"},
                },
                "required": ["name", "from", "balance", "created"],
            },
            "get_names_response": {"type": "array", "items": {"type": "string"}},
        }
    },
}

TYPES = {
    "Name": "my_types.Name",
    "BigInt": "my_types.BigInt",
    "Time": "my_types.Time",
    "Id": "my_types.Id",
}


def custom_types(**overrides: Any) -> CustomTypes:
    return CustomTypes(
        **{"types": TYPES, "extension": "x-test-type", "format_types": {"date-time": "Time"}, **overrides}
    )


def generate(tmp_path: Path, model_options: ModelOptions, types: CustomTypes | None) -> str:
    openapi_file = tmp_path / "openapi.json"
    openapi_file.write_text(json.dumps(OPENAPI))
    output = tmp_path / "description.py"
    generate_api_description(
        "test_api_description",
        openapi_file,
        output,
        allow_passing_item_suffix=False,
        model_options=model_options,
        custom_types=types,
    )
    return output.read_text()


def classes(source: str) -> dict[str, ast.ClassDef]:
    return {node.name: node for node in ast.parse(source).body if isinstance(node, ast.ClassDef)}


def annotation(class_node: ast.ClassDef, field_name: str) -> str:
    for statement in class_node.body:
        if isinstance(statement, ast.AnnAssign) and ast.unparse(statement.target) == field_name:
            return ast.unparse(statement.annotation)
    raise AssertionError(f"{field_name} not found")


def test_custom_types_are_applied_by_extension_ref_and_format() -> None:
    # ACT
    applied = custom_types().apply(OPENAPI)

    # ASSERT
    response = applied["components"]["schemas"]["get_account_response"]["properties"]
    assert response["name"]["customTypePath"] == "my_types.Name"
    assert response["balance"]["customTypePath"] == "my_types.BigInt"  # from the referenced component
    assert response["created"]["customTypePath"] == "my_types.Time"  # from format
    assert "customTypePath" not in response["comment"]
    assert "customTypePath" not in OPENAPI["components"]["schemas"]["get_account_response"]["properties"]["name"]


def test_custom_types_can_be_skipped_in_unions() -> None:
    # ACT
    applied = custom_types(skip_in_unions=True).apply(OPENAPI)
    applied_in_unions = custom_types().apply(OPENAPI)

    # ASSERT
    union = "/".join(["get_account_response", "properties", "id_or_object"])
    member = applied["components"]["schemas"]["get_account_response"]["properties"]["id_or_object"]["oneOf"][0]
    assert "customTypePath" not in member, union
    member = applied_in_unions["components"]["schemas"]["get_account_response"]["properties"]["id_or_object"]["oneOf"][
        0
    ]
    assert member["customTypePath"] == "my_types.Id"


def test_unknown_custom_type_raises() -> None:
    # ACT & ASSERT
    with pytest.raises(UnknownCustomTypeError, match="Name"):
        custom_types(types={"BigInt": "my_types.BigInt", "Time": "my_types.Time", "Id": "my_types.Id"}).apply(OPENAPI)


def test_dataclass_models_with_base_class_and_custom_types(tmp_path: Path) -> None:
    # ACT
    source = generate(
        tmp_path,
        ModelOptions(model_type="dataclass", base_class="my_base.Model", frozen=True, kw_only=True),
        custom_types(),
    )

    # ASSERT
    response = classes(source)["GetAccountResponse"]
    assert [ast.unparse(base) for base in response.bases] == ["Model"]
    assert [ast.unparse(decorator) for decorator in response.decorator_list] == ["dataclass(frozen=True, kw_only=True)"]
    assert annotation(response, "name") == "Name"
    assert annotation(response, "balance") == "BigInt"
    assert annotation(response, "created") == "Time"
    assert annotation(response, "from_") == "str"
    assert "from my_base import Model" in source
    assert "from my_types import" in source


def test_msgspec_models_with_base_class(tmp_path: Path) -> None:
    # ACT
    source = generate(tmp_path, ModelOptions(model_type="msgspec", base_class="my_base.Struct2", kw_only=True), None)

    # ASSERT
    response = classes(source)["GetAccountResponse"]
    assert [ast.unparse(base) for base in response.bases] == ["Struct2"]
    assert [ast.unparse(keyword) for keyword in response.keywords] == ["kw_only=True"]
    assert annotation(response, "name") == "str"


def test_array_result_without_item_model_is_not_marked_as_response_array(tmp_path: Path) -> None:
    # ACT
    source = generate(tmp_path, ModelOptions(), None)

    # ASSERT
    description = source[source.index("test_api_description = ") :]
    get_names = description[description.index('"get_names"') :]
    assert '"result": GetNamesResponse,' in get_names
    assert '"response_array"' not in get_names[: get_names.index("}")]


def test_model_helpers_support_structs_and_dataclasses() -> None:
    # ARRANGE
    import dataclasses

    import msgspec

    class StructModel(msgspec.Struct):
        a: int
        b: str = "x"

    @dataclasses.dataclass
    class DataclassModel:
        a: int
        b: str = "x"

    # ACT & ASSERT
    for model in (StructModel, DataclassModel):
        assert is_model(model)
        fields = model_fields(model)
        assert [(field.name, field.type, field.default) for field in fields] == [
            ("a", int, msgspec.NODEFAULT),
            ("b", str, "x"),
        ]
    assert not is_model(int)
    assert not is_model(list[int])
