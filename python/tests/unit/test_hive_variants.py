from __future__ import annotations

from api_client_generator import hive_variants


def test_variants_map_types_of_hive_to_their_forms_in_schemas() -> None:
    # ACT
    public = hive_variants.public_custom_types(["AccountName"], {"Hf26Operation": "pkg.operations.Hf26Operation"})
    validation = hive_variants.validation_custom_types(["AccountName"])

    # ASSERT
    assert public.types == {
        "AccountName": "schemas.fields.public.AccountName",
        "Hf26Operation": "pkg.operations.Hf26Operation",
    }
    assert validation.types == {"AccountName": "schemas.fields.validation.AccountName"}
    assert public.extension == validation.extension == "x-hive-type"
    assert public.format_types == validation.format_types == {"date-time": "HiveDateTime"}
    assert (public.skip_in_unions, validation.skip_in_unions) == (False, True)


def test_public_models_are_dataclasses_with_fields_not_named_as_methods_of_hive_models() -> None:
    # ACT
    options = hive_variants.public_model_options("pkg._base.HiveModel")

    # ASSERT
    assert (options.model_type, options.base_class) == ("dataclass", "pkg._base.HiveModel")
    assert options.reserved_field_names == {"from_builtins", "parse_raw", "to_builtins", "dict", "json", "copy"}
    assert hive_variants.VALIDATION_MODEL_OPTIONS.model_type == "msgspec"
