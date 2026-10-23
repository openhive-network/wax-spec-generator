"""
Variants of models of Hive APIs - public and validation models generated from the same OpenAPI definition.

- public: dataclasses (`HiveModel` of hiveio_api) with builtin types expressed by aliases of `schemas.fields.public`
  (e.g. `AccountName = str`) - returned by API calls, never validated,
- validation: msgspec models (`PreconfiguredBaseModel` of schemas) with validation forms of the types
  (`schemas.fields.validation`, e.g. `AccountName` validated by msgspec itself) - used only to validate responses.

Both map the `x-hive-type` annotations and dates (`format: date-time`) of Hive definitions to types of schemas of the
same name. Types are referred to by import paths, so the generator does not depend on schemas - callers give the names
of the types (`__all__` of the module of the variant).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from api_client_generator.model_options import CustomTypes, ModelOptions

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

HIVE_TYPE_EXTENSION: Final[str] = "x-hive-type"
FORMAT_TYPES: Final[Mapping[str, str]] = {"date-time": "HiveDateTime"}

PUBLIC_BASE_CLASS: Final[str] = "hiveio_api.HiveModel"
PUBLIC_TYPES_MODULE: Final[str] = "schemas.fields.public"
HIVE_MODEL_METHODS: Final[frozenset[str]] = frozenset(
    {"from_builtins", "parse_raw", "to_builtins", "dict", "json", "copy"}
)
"""Public methods of `HiveModel` - fields of public models of these names get a trailing underscore."""

VALIDATION_BASE_CLASS: Final[str] = "schemas._preconfigured_base_model.PreconfiguredBaseModel"
VALIDATION_TYPES_MODULE: Final[str] = "schemas.fields.validation"
VALIDATION_MODEL_OPTIONS: Final[ModelOptions] = ModelOptions(
    model_type="msgspec", base_class=VALIDATION_BASE_CLASS, kw_only=True, enum_as_literal=True
)


def public_model_options(base_class: str = PUBLIC_BASE_CLASS) -> ModelOptions:
    """
    Options of public models - enums as `Literal`, so values of public models are plain builtins.

    Args:
        base_class: Import path of `HiveModel` (inside hiveio_api - of its defining module, not of the package).
    """
    return ModelOptions(
        model_type="dataclass",
        base_class=base_class,
        kw_only=True,
        enum_as_literal=True,
        reserved_field_names=HIVE_MODEL_METHODS,
    )


def public_custom_types(type_names: Iterable[str], types: Mapping[str, str] | None = None) -> CustomTypes:
    """
    Custom types of public models - aliases of builtin types.

    Args:
        type_names: Names of the types of schemas (`schemas.fields.public.__all__`).
        types: Further custom types (name -> import path), e.g. models of operations.
    """
    return _custom_types(PUBLIC_TYPES_MODULE, type_names, types)


def validation_custom_types(type_names: Iterable[str], types: Mapping[str, str] | None = None) -> CustomTypes:
    """
    Custom types of validation models - validation forms of the types.

    Members of unions with other types keep their builtin type - msgspec does not support such unions.

    Args:
        type_names: Names of the types of schemas (`schemas.fields.validation.__all__`).
        types: Further custom types (name -> import path), e.g. models of operations.
    """
    return _custom_types(VALIDATION_TYPES_MODULE, type_names, types, skip_in_unions=True)


def _custom_types(
    module: str, type_names: Iterable[str], types: Mapping[str, str] | None, *, skip_in_unions: bool = False
) -> CustomTypes:
    return CustomTypes(
        types={name: f"{module}.{name}" for name in type_names} | dict(types or {}),
        extension=HIVE_TYPE_EXTENSION,
        format_types=FORMAT_TYPES,
        skip_in_unions=skip_in_unions,
    )
