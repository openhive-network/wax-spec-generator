"""
Options controlling the shape of generated models.

Both options are independent of any concrete API - the caller decides which model type, base class and custom
types are used, so the same OpenAPI definition can be turned into differently shaped model sets
(e.g. plain dataclasses for users and msgspec structs for validation).
"""

from __future__ import annotations

import copy
import dataclasses
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final, Literal

from datamodel_code_generator import DataModelType, InputFileType, PythonVersion
from msgspec import NODEFAULT, Struct
from msgspec.structs import fields as struct_fields

from api_client_generator.exceptions import UnknownCustomTypeError

if TYPE_CHECKING:
    from collections.abc import Mapping

ModelType = Literal["msgspec", "dataclass"]

_COMPONENT_REF_PREFIX: Final[str] = "#/components/schemas/"
_CUSTOM_TYPE_PATH_KEY: Final[str] = "customTypePath"
_UNION_KEYS: Final[frozenset[str]] = frozenset({"oneOf", "anyOf"})


def _has_multiple_non_null_members(members: Any) -> bool:
    if not isinstance(members, list):
        return False
    return len([member for member in members if not (isinstance(member, dict) and member.get("type") == "null")]) > 1


@dataclass(frozen=True)
class ModelOptions:
    """
    Shape of the generated model classes.

    Args:
        model_type: `msgspec` generates `msgspec.Struct` subclasses, `dataclass` generates `@dataclass` classes.
        base_class: Dotted import path of the base class for every generated model (e.g. `my_pkg.base.Model`).
                    For `msgspec` it must be a `msgspec.Struct` subclass.
        frozen: Generate immutable models (only for `dataclass`).
        kw_only: Generate keyword-only models.
    """

    model_type: ModelType = "msgspec"
    base_class: str | None = None
    frozen: bool = False
    kw_only: bool = False

    @property
    def base_class_name(self) -> str:
        """Name under which generated code refers to the base class (`Struct` for plain msgspec models)."""
        if self.base_class is not None:
            return self.base_class.rpartition(".")[2]
        return "Struct" if self.model_type == "msgspec" else "object"

    def generate_kwargs(self) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "output_model_type": DataModelType.MsgspecStruct
            if self.model_type == "msgspec"
            else DataModelType.DataclassesDataclass,
            "input_file_type": InputFileType.OpenAPI,
            "use_field_description": True,
            "use_standard_collections": True,
            "use_exact_imports": True,
            "target_python_version": PythonVersion.PY_311,
        }
        if self.base_class is not None:
            kwargs["base_class"] = self.base_class
        if self.kw_only:
            kwargs["keyword_only"] = True
        if self.frozen and self.model_type == "dataclass":
            kwargs["frozen_dataclasses"] = True
        return kwargs


@dataclass(frozen=True)
class CustomTypes:
    """
    Replace OpenAPI types of chosen schema nodes with caller-provided types.

    Args:
        types: Name of a custom type -> dotted import path of the class/alias used in generated code.
        extension: Vendor extension key (e.g. `x-my-type`) whose value is a name from `types`. It can be placed on
                   a component (applies everywhere the component is used) or on a property (wins over the component).
        format_types: OpenAPI `format` -> name from `types`, applied to nodes without an extension.
        skip_in_unions: Do not apply custom types to members of `oneOf`/`anyOf` having other non-null members
                        (msgspec does not support unions of custom types with other types).

    Notes:
        Names which are not present in `types` raise `UnknownCustomTypeError`, so every annotation in the definition
        has to be covered by the caller.
    """

    types: Mapping[str, str] = field(default_factory=dict)
    extension: str | None = None
    format_types: Mapping[str, str] = field(default_factory=dict)
    skip_in_unions: bool = False

    def apply(self, openapi: dict[str, Any]) -> dict[str, Any]:
        """Return a copy of the definition with `customTypePath` set on the nodes which get a custom type."""
        result = copy.deepcopy(openapi)
        components: dict[str, Any] = result.get("components", {}).get("schemas", {})
        self._walk(result, components)
        return result

    def apply_to_file(self, openapi_file: Path, output_file: Path) -> None:
        output_file.write_text(json.dumps(self.apply(json.loads(openapi_file.read_text()))))

    def _walk(self, node: Any, components: Mapping[str, Any], *, in_union: bool = False) -> None:
        if isinstance(node, list):
            for item in node:
                self._walk(item, components, in_union=in_union)
            return
        if not isinstance(node, dict):
            return

        skipped = self.skip_in_unions and in_union
        if not skipped and (name := self._resolve_name(node, components)) is not None:
            node[_CUSTOM_TYPE_PATH_KEY] = self._path_for(name)

        for key, value in node.items():
            self._walk(value, components, in_union=key in _UNION_KEYS and _has_multiple_non_null_members(value))

    def _resolve_name(self, node: Mapping[str, Any], components: Mapping[str, Any]) -> str | None:
        if self.extension is not None and isinstance(name := node.get(self.extension), str):
            return name

        ref = node.get("$ref")
        if self.extension is not None and isinstance(ref, str) and ref.startswith(_COMPONENT_REF_PREFIX):
            target = components.get(ref.removeprefix(_COMPONENT_REF_PREFIX), {})
            if isinstance(target, dict) and isinstance(name := target.get(self.extension), str):
                return name

        format_ = node.get("format")
        if isinstance(format_, str) and format_ in self.format_types:
            return self.format_types[format_]
        return None

    def _path_for(self, name: str) -> str:
        if name not in self.types:
            raise UnknownCustomTypeError(name, tuple(self.types))
        return self.types[name]


@dataclass(frozen=True)
class ModelField:
    name: str
    type: Any
    default: Any


def is_model(potential_model: Any) -> bool:
    """Check whether the given object is a generated model class (msgspec struct or dataclass)."""
    if not isinstance(potential_model, type):
        return False
    return issubclass(potential_model, Struct) or dataclasses.is_dataclass(potential_model)


def model_fields(model: type[Any]) -> list[ModelField]:
    """Fields of a model in declaration order; `default` is `msgspec.NODEFAULT` for required fields."""
    if issubclass(model, Struct):
        return [ModelField(field_.name, field_.type, field_.default) for field_ in struct_fields(model)]

    from typing import get_type_hints  # noqa: PLC0415

    hints = get_type_hints(model)
    result: list[ModelField] = []
    for field_ in dataclasses.fields(model):
        default: Any = NODEFAULT
        if field_.default is not dataclasses.MISSING:
            default = field_.default
        elif field_.default_factory is not dataclasses.MISSING:
            default = field_.default_factory()
        result.append(ModelField(field_.name, hints[field_.name], default))
    return result
