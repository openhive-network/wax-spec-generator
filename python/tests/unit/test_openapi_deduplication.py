from __future__ import annotations

from typing import TYPE_CHECKING, Final

import pytest

from api_client_generator.openapi_flattening import flatten_openapi

from .helpers import annotation, classes, definition, generate_description, schemas_of

if TYPE_CHECKING:
    from pathlib import Path

MANABAR: Final[dict[str, object]] = {
    "type": "object",
    "properties": {"current_mana": {"type": "integer"}, "last_update_time": {"type": "integer"}},
    "required": ["current_mana", "last_update_time"],
}


def properties_of(flattened: dict[str, object], name: str) -> dict[str, object]:
    schema = schemas_of(flattened)[name]
    assert isinstance(schema, dict)
    properties = schema["properties"]
    assert isinstance(properties, dict)
    return properties


def test_schemas_equal_to_a_component_refer_to_it_with_their_descriptions() -> None:
    # ARRANGE
    openapi = definition(
        {
            "manabar": MANABAR,
            "account": {
                "type": "object",
                "properties": {
                    "voting": {"$ref": "#/components/schemas/manabar", "description": "Voting manabar."},
                    # written again, with other documentation and other order of keys - the same structure
                    "downvote": {
                        "type": "object",
                        "description": "Downvote manabar.",
                        "required": ["last_update_time", "current_mana"],
                        "properties": {
                            "last_update_time": {"type": "integer", "example": 1},
                            "current_mana": {"type": "integer", "description": "Mana."},
                        },
                    },
                },
            },
        }
    )

    # ACT
    flattened = flatten_openapi(openapi, deduplicate=True)

    # ASSERT
    assert properties_of(flattened, "account") == {
        "voting": {"$ref": "#/components/schemas/manabar", "description": "Voting manabar."},
        "downvote": {"$ref": "#/components/schemas/manabar", "description": "Downvote manabar."},
    }
    assert schemas_of(flattened)["manabar"] == MANABAR


def test_schemas_differing_in_structure_are_kept() -> None:
    # ARRANGE
    legacy_manabar = {
        **MANABAR,
        "properties": {"current_mana": {"type": "string"}, "last_update_time": {"type": "integer"}},
    }
    openapi = definition(
        {
            "manabar": MANABAR,
            "account": {"type": "object", "properties": {"voting": legacy_manabar, "rc": legacy_manabar}},
            "other": {"type": "object", "properties": {"voting": {"$ref": "#/components/schemas/manabar"}}},
        }
    )

    # ACT
    flattened = flatten_openapi(openapi, deduplicate=True)

    # ASSERT
    assert properties_of(flattened, "other")["voting"] == {"$ref": "#/components/schemas/manabar"}
    assert properties_of(flattened, "account")["voting"] == {"$ref": "#/components/schemas/voting"}
    assert schemas_of(flattened)["voting"] == legacy_manabar


def test_repeated_schemas_without_a_component_become_a_component_named_after_their_property() -> None:
    # ARRANGE
    authority = {
        "type": "object",
        "properties": {
            "weight_threshold": {"type": "integer"},
            "key_auths": {"type": "array", "items": {"type": "string"}},
        },
    }
    openapi = definition(
        {
            "account": {"type": "object", "properties": {"owner": authority, "active": authority}},
            "request": {"type": "object", "properties": {"owner": authority}},
        }
    )

    # ACT
    flattened = flatten_openapi(openapi, deduplicate=True)

    # ASSERT
    assert properties_of(flattened, "account") == {
        "owner": {"$ref": "#/components/schemas/owner"},
        "active": {"$ref": "#/components/schemas/owner"},
    }
    assert properties_of(flattened, "request") == {"owner": {"$ref": "#/components/schemas/owner"}}
    assert schemas_of(flattened)["owner"] == authority


def test_repeated_elements_of_arrays_are_named_after_the_singular_form_of_the_property() -> None:
    # ARRANGE
    beneficiary = {"type": "object", "properties": {"account": {"type": "string"}, "weight": {"type": "integer"}}}
    beneficiaries = {"type": "array", "items": beneficiary}
    openapi = definition(
        {
            "comment": {"type": "object", "properties": {"beneficiaries": beneficiaries}},
            "post": {"type": "object", "properties": {"beneficiaries": beneficiaries}},
        }
    )

    # ACT
    flattened = flatten_openapi(openapi, deduplicate=True)

    # ASSERT
    assert properties_of(flattened, "comment")["beneficiaries"] == {
        "type": "array",
        "items": {"$ref": "#/components/schemas/beneficiary"},
    }
    assert schemas_of(flattened)["beneficiary"] == beneficiary


def test_name_of_a_new_component_taken_by_another_component_is_qualified_by_the_holder() -> None:
    # ARRANGE
    pair = {"type": "object", "properties": {"base": {"type": "string"}, "quote": {"type": "string"}}}
    openapi = definition(
        {
            "price": {"type": "integer"},
            "feed": {
                "type": "object",
                "properties": {"price": pair, "median": {"type": "object", "properties": {"price": pair}}},
            },
        }
    )

    # ACT
    flattened = flatten_openapi(openapi, deduplicate=True)

    # ASSERT
    assert properties_of(flattened, "feed")["price"] == {"$ref": "#/components/schemas/feed_price"}
    assert schemas_of(flattened)["price"] == {"type": "integer"}


def test_schemas_holding_equal_schemas_are_equal() -> None:
    # ARRANGE
    openapi = definition(
        {
            "manabar": MANABAR,
            "account": {
                "type": "object",
                "properties": {
                    "first": {"type": "object", "properties": {"mana": MANABAR, "name": {"type": "string"}}},
                    "second": {"type": "object", "properties": {"mana": MANABAR, "name": {"type": "string"}}},
                },
            },
        }
    )

    # ACT
    flattened = flatten_openapi(openapi, deduplicate=True)

    # ASSERT
    assert properties_of(flattened, "account") == {
        "first": {"$ref": "#/components/schemas/first"},
        "second": {"$ref": "#/components/schemas/first"},
    }
    assert properties_of(flattened, "first")["mana"] == {"$ref": "#/components/schemas/manabar"}


def test_arrays_with_properties_are_not_models() -> None:
    # ARRANGE
    pair = {"type": "array", "properties": {"type": {"type": "string"}}, "items": {"type": "string"}}
    openapi = definition({"block": {"type": "object", "properties": {"first": pair, "second": pair}}})

    # ACT
    flattened = flatten_openapi(openapi, deduplicate=True)

    # ASSERT
    assert properties_of(flattened, "block") == {"first": pair, "second": pair}
    assert set(schemas_of(flattened)) == {"block"}


@pytest.mark.parametrize(("extension", "is_model"), [("x-test-type", False), ("x-other-type", True)])
def test_only_schemas_with_the_extension_of_custom_types_are_not_models(extension: str, is_model: bool) -> None:
    # ARRANGE
    tagged = {**MANABAR, "x-test-type": "Manabar"}
    openapi = definition({"account": {"type": "object", "properties": {"voting": tagged, "downvote": tagged}}})

    # ACT
    flattened = flatten_openapi(openapi, deduplicate=True, custom_type_extension=extension)

    # ASSERT
    expected = {"$ref": "#/components/schemas/voting"} if is_model else tagged
    assert properties_of(flattened, "account") == {"voting": expected, "downvote": expected}
    assert set(schemas_of(flattened)) == ({"account", "voting"} if is_model else {"account"})


def test_of_equal_components_the_most_referenced_one_is_used() -> None:
    # ARRANGE
    openapi = definition(
        {
            "a_manabar": MANABAR,
            "manabar": MANABAR,
            "account": {
                "type": "object",
                "properties": {
                    "voting": {"$ref": "#/components/schemas/manabar"},
                    "rc": {"$ref": "#/components/schemas/manabar"},
                    "downvote": {"$ref": "#/components/schemas/a_manabar"},
                },
            },
        }
    )

    # ACT
    flattened = flatten_openapi(openapi, deduplicate=True)

    # ASSERT
    assert {value["$ref"] for value in properties_of(flattened, "account").values()} == {  # type: ignore[index]
        "#/components/schemas/manabar"
    }
    assert schemas_of(flattened)["a_manabar"] == MANABAR


def test_one_model_is_generated_for_equal_schemas(tmp_path: Path) -> None:
    # ARRANGE
    openapi = definition(
        {
            "voting_manabar": MANABAR,
            "get_account": {"type": "object", "properties": {"name": {"type": "string"}}},
            "get_account_response": {
                "type": "object",
                "properties": {
                    "voting_manabar": {"$ref": "#/components/schemas/voting_manabar"},
                    "downvote_manabar": {"$ref": "#/components/schemas/voting_manabar"},
                    "rc_manabar": MANABAR,
                },
            },
        },
        {"api.get_account": ("get_account", "get_account_response")},
    )

    # ACT
    output = generate_description(tmp_path, openapi, flatten=True, deduplicate_models=True)

    # ASSERT
    models = classes(output.read_text())
    assert "VotingManabar" in models
    assert not {"DownvoteManabar", "RcManabar"} & set(models)
    response = models["GetAccountResponse"]
    fields = ("voting_manabar", "downvote_manabar", "rc_manabar")
    assert {annotation(response, name).split(" | ")[0] for name in fields} == {"VotingManabar"}
