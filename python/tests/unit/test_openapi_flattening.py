from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from api_client_generator.exceptions import OpenApiFlatteningError
from api_client_generator.openapi_flattening import flatten_openapi

from .helpers import classes, definition, generate_description, schemas_of

if TYPE_CHECKING:
    from pathlib import Path


def schema(flattened: dict[str, object], name: str) -> object:
    return schemas_of(flattened)[name]


def test_refs_are_replaced_with_referenced_schemas() -> None:
    # ARRANGE
    openapi = definition(
        {
            "name": {"type": "string", "description": "Name of the account."},
            "account": {"type": "object", "properties": {"name": {"$ref": "#/components/schemas/name"}}},
        }
    )

    # ACT
    flattened = flatten_openapi(openapi)

    # ASSERT
    assert schema(flattened, "account") == {
        "type": "object",
        "properties": {"name": {"type": "string", "description": "Name of the account."}},
    }
    assert "$ref" in json.dumps(openapi), "the given definition is not changed"


def test_keys_next_to_a_ref_win_when_the_value_is_resolved_for_the_first_time() -> None:
    # ARRANGE
    openapi = definition(
        {
            "name": {"type": "string", "description": "Shared description."},
            "account": {
                "type": "object",
                "properties": {"name": {"$ref": "#/components/schemas/name", "description": "Own description."}},
            },
        }
    )

    # ACT
    flattened = flatten_openapi(openapi)

    # ASSERT
    account = schema(flattened, "account")
    assert isinstance(account, dict)
    assert account["properties"] == {"name": {"description": "Own description.", "type": "string"}}


def test_keys_next_to_a_ref_are_only_added_when_a_plain_ref_resolved_the_value_before() -> None:
    # ARRANGE
    openapi = definition(
        {
            "name": {"type": "string", "description": "Shared description."},
            "account": {
                "type": "object",
                "properties": {
                    "creator": {"$ref": "#/components/schemas/name"},
                    "name": {"$ref": "#/components/schemas/name", "description": "Own description.", "example": "a"},
                },
            },
        }
    )

    # ACT
    flattened = flatten_openapi(openapi)

    # ASSERT
    account = schema(flattened, "account")
    assert isinstance(account, dict)
    assert account["properties"] == {
        "creator": {"type": "string", "description": "Shared description."},
        "name": {"type": "string", "description": "Shared description.", "example": "a"},
    }


def test_aliases_are_resolved_to_the_aliased_schemas() -> None:
    # ARRANGE
    openapi = definition(
        {
            "block": {"type": "object", "properties": {"id": {"type": "string"}}},
            "get_block_response": {"$ref": "#/components/schemas/block"},
            "response": {
                "type": "object",
                "properties": {"result": {"$ref": "#/components/schemas/get_block_response"}},
            },
        }
    )

    # ACT
    flattened = flatten_openapi(openapi)

    # ASSERT
    response = schema(flattened, "response")
    assert isinstance(response, dict)
    assert response["properties"] == {"result": {"type": "object", "properties": {"id": {"type": "string"}}}}


def test_all_of_is_merged_into_one_schema() -> None:
    # ARRANGE
    openapi = definition(
        {
            "base": {
                "type": "object",
                "description": "Base.",
                "properties": {"b": {"type": "string"}},
                "required": ["b"],
            },
            "derived": {
                "description": "Derived.",
                "allOf": [
                    {"$ref": "#/components/schemas/base"},
                    {"type": "object", "properties": {"a": {"type": "integer"}}, "required": ["a"]},
                ],
            },
        }
    )

    # ACT
    flattened = flatten_openapi(openapi)

    # ASSERT
    derived = schema(flattened, "derived")
    assert isinstance(derived, dict)
    assert list(derived) == ["description", "type", "required", "properties"]
    assert list(derived["properties"]) == ["b", "a"], "properties of the referenced schema first"
    assert derived == {
        "description": "Derived.",
        "type": "object",
        "required": ["a", "b"],
        "properties": {"b": {"type": "string"}, "a": {"type": "integer"}},
    }


def test_equal_values_of_all_of_members_are_merged_once() -> None:
    # ARRANGE
    member = {
        "type": "object",
        "example": {"name": "alice"},
        "properties": {"name": {"type": "string", "example": "alice"}},
    }
    openapi = definition({"account": {"allOf": [member, json.loads(json.dumps(member))]}})

    # ACT
    flattened = flatten_openapi(openapi)

    # ASSERT
    assert schema(flattened, "account") == member


def test_constraints_of_all_of_members_are_combined() -> None:
    # ARRANGE
    openapi = definition(
        {
            "names": {
                "allOf": [
                    {
                        "type": "object",
                        "minProperties": 1,
                        "maxProperties": 9,
                        "properties": {
                            "kind": {"type": "string", "enum": ["a", "b", "c"], "minLength": 1, "maxLength": 5}
                        },
                        "additionalProperties": {"type": "string", "maxLength": 8},
                    },
                    {
                        "minProperties": 2,
                        "properties": {"kind": {"enum": ["c", "b"], "minLength": 2, "maxLength": 9}},
                        "additionalProperties": {"type": "string", "maxLength": 4},
                    },
                ]
            }
        }
    )

    # ACT
    flattened = flatten_openapi(openapi)

    # ASSERT
    assert schema(flattened, "names") == {
        "type": "object",
        "minProperties": 2,
        "maxProperties": 9,
        "additionalProperties": {"type": "string", "maxLength": 4},
        "properties": {"kind": {"type": "string", "enum": ["b", "c"], "minLength": 2, "maxLength": 5}},
    }


def test_type_of_the_last_all_of_member_wins() -> None:
    # ARRANGE
    openapi = definition(
        {
            "extensions": {
                "allOf": [
                    {"type": "object", "properties": {"type": {"type": "string"}}},
                    {"type": "array", "items": {"type": "string"}},
                ]
            }
        }
    )

    # ACT
    flattened = flatten_openapi(openapi)

    # ASSERT
    assert schema(flattened, "extensions") == {
        "type": "array",
        "properties": {"type": {"type": "string"}},
        "items": {"type": "string"},
    }


def test_nullable_any_of_is_kept() -> None:
    # ARRANGE
    openapi = definition(
        {
            "name": {"type": "string"},
            "account": {
                "type": "object",
                "properties": {
                    "name": {
                        "anyOf": [{"type": "null", "description": "No name."}, {"$ref": "#/components/schemas/name"}]
                    }
                },
            },
        }
    )

    # ACT
    flattened = flatten_openapi(openapi)

    # ASSERT
    account = schema(flattened, "account")
    assert isinstance(account, dict)
    assert account["properties"] == {"name": {"anyOf": [{"type": "null"}, {"type": "string"}]}}


def test_other_any_of_is_kept_as_a_union() -> None:
    # ARRANGE
    openapi = definition(
        {
            "name": {"type": "string"},
            "id": {"description": "Id.", "anyOf": [{"$ref": "#/components/schemas/name"}, {"type": "integer"}]},
        }
    )

    # ACT
    flattened = flatten_openapi(openapi)

    # ASSERT
    assert schema(flattened, "id") == {"description": "Id.", "anyOf": [{"type": "string"}, {"type": "integer"}]}


@pytest.mark.parametrize(
    ("schemas", "message"),
    [
        ({"node": {"type": "object", "properties": {"child": {"$ref": "#/components/schemas/node"}}}}, "Circular"),
        ({"account": {"$ref": "other.json#/components/schemas/account"}}, "outside the definition"),
        ({"account": {"$ref": "#/components/schemas/missing"}}, "points to nothing"),
    ],
)
def test_references_which_cannot_be_flattened_raise(schemas: dict[str, object], message: str) -> None:
    # ACT & ASSERT
    with pytest.raises(OpenApiFlatteningError, match=message):
        flatten_openapi(definition(schemas))


def test_incompatible_all_of_members_raise() -> None:
    # ARRANGE
    openapi = definition({"id": {"allOf": [{"x-hive-type": "AccountName"}, {"x-hive-type": "PublicKey"}]}})

    # ACT & ASSERT
    with pytest.raises(OpenApiFlatteningError, match="x-hive-type"):
        flatten_openapi(openapi)


WALLETS_API = definition(
    {
        "list_wallets": {"type": "object", "properties": {}},
        "wallet_details": {
            "type": "object",
            "properties": {"name": {"type": "string"}, "unlocked": {"type": "boolean"}},
            "required": ["name", "unlocked"],
        },
        "list_wallets_response": {
            "type": "object",
            "properties": {"wallets": {"type": "array", "items": {"$ref": "#/components/schemas/wallet_details"}}},
            "required": ["wallets"],
        },
    },
    {"test_api.list_wallets": ("list_wallets", "list_wallets_response")},
)


def generated_classes(tmp_path: Path, *, flatten: bool) -> set[str]:
    return set(
        classes(generate_description(tmp_path, WALLETS_API, f"description_{flatten}", flatten=flatten).read_text())
    )


def test_models_generated_from_the_flattened_definition_are_named_after_properties(tmp_path: Path) -> None:
    # ACT
    flattened = generated_classes(tmp_path, flatten=True)
    not_flattened = generated_classes(tmp_path, flatten=False)

    # ASSERT
    assert "Wallet" in flattened
    assert "WalletDetails" not in flattened
    assert "WalletDetails" in not_flattened
