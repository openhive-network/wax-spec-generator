"""
Options controlling the shape of generated models.

Both options are independent of any concrete API - the caller decides which model type, base class and custom
types are used, so the same OpenAPI definition can be turned into differently shaped model sets
(e.g. plain dataclasses for users and msgspec structs for validation).
"""

from __future__ import annotations

import ast
import copy
import dataclasses
import json
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Final, Literal, NotRequired, TypedDict

from datamodel_code_generator import InputFileType, LiteralType, PythonVersion
from datamodel_code_generator.enums import DataModelType
from datamodel_code_generator.format import Formatter
from datamodel_code_generator.model.base import ALL_MODEL
from msgspec import NODEFAULT, Struct
from msgspec.structs import fields as struct_fields

from api_client_generator.exceptions import UnknownCustomTypeError
from api_client_generator.openapi_schema import component_schemas, referenced_component

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

ModelType = Literal["msgspec", "dataclass"]

TEMPLATES_DIRECTORY: Final[Path] = Path(__file__).parent / "_private" / "templates"
"""Custom datamodel-code-generator templates (dataclass fields keep their original JSON keys in metadata)."""
ALIAS_METADATA_KEY: Final[str] = "alias"
"""
Key of `dataclasses.field` metadata of dataclass fields renamed in Python (e.g. `from` -> `from_`) holding their JSON key
(msgspec models keep it in `msgspec.field(name=...)`).
"""
_CUSTOM_TYPE_PATH_KEY: Final[str] = "customTypePath"
_UNION_KEYS: Final[frozenset[str]] = frozenset({"oneOf", "anyOf"})


class GenerateKwargs(TypedDict):
    """Options of `datamodel_code_generator.generate` set by `ModelOptions`."""

    output_model_type: DataModelType
    input_file_type: InputFileType
    use_field_description: bool
    use_standard_collections: bool
    use_exact_imports: bool
    target_python_version: PythonVersion
    disable_timestamp: bool
    formatters: list[Formatter]
    base_class: NotRequired[str]
    keyword_only: NotRequired[bool]
    custom_template_dir: NotRequired[Path]
    use_schema_description: NotRequired[bool]
    aliases: NotRequired[dict[str, str]]
    extra_template_data: NotRequired[defaultdict[str, dict[str, str]]]
    frozen_dataclasses: NotRequired[bool]
    enum_field_as_literal: NotRequired[LiteralType]


def _has_multiple_non_null_members(members: object) -> bool:
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
        enum_as_literal: Generate enums as `Literal[...]` of their values instead of `Enum` classes (values stay plain
                         builtins, e.g. for models built from parsed JSON without conversion).
        reserved_field_names: Names which cannot be names of fields (e.g. methods of `base_class`, see
                              `hive_variants.HIVE_MODEL_METHODS`) - such fields get a trailing underscore, like Python
                              keywords, and keep their JSON key as an alias.

    Raises:
        ValueError: If `frozen` is given for `msgspec` models.
    """

    model_type: ModelType = "msgspec"
    base_class: str | None = None
    frozen: bool = False
    kw_only: bool = False
    enum_as_literal: bool = False
    reserved_field_names: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        if self.frozen and self.model_type != "dataclass":
            raise ValueError(f"Frozen models are supported only for dataclasses, not for {self.model_type}.")

    @property
    def base_class_name(self) -> str:
        """Name under which generated code refers to the base class (`Struct` for plain msgspec models)."""
        if self.base_class is not None:
            return self.base_class.rpartition(".")[2]
        return "Struct" if self.model_type == "msgspec" else "object"

    def generate_kwargs(self) -> GenerateKwargs:
        """
        Keyword arguments of `datamodel_code_generator.generate` producing models of this shape.

        Dataclass fields renamed in Python (e.g. `from` -> `from_`) keep their original key in
        `field(metadata={ALIAS_METADATA_KEY: ...})`. Dataclasses always get a docstring (the description of their
        schema or a generic one) - `dataclass` computes the signature of classes without it for `__doc__`, which is
        a large part of the import time of generated modules.
        """
        kwargs: GenerateKwargs = {
            "output_model_type": DataModelType.MsgspecStruct
            if self.model_type == "msgspec"
            else DataModelType.DataclassesDataclass,
            "input_file_type": InputFileType.OpenAPI,
            "use_field_description": True,
            "use_standard_collections": True,
            "use_exact_imports": True,
            "target_python_version": PythonVersion.PY_311,
            "disable_timestamp": True,  # the same definition gives the same modules
            "formatters": [],  # generated modules are formatted with ruff afterwards
        }
        if self.base_class is not None:
            kwargs["base_class"] = self.base_class
        if self.kw_only:
            kwargs["keyword_only"] = True
        if self.model_type == "dataclass":
            kwargs["custom_template_dir"] = TEMPLATES_DIRECTORY
            kwargs["use_schema_description"] = True
            kwargs["extra_template_data"] = defaultdict(dict, {ALL_MODEL: {"alias_metadata_key": ALIAS_METADATA_KEY}})
        if self.frozen:
            kwargs["frozen_dataclasses"] = True
        if self.enum_as_literal:
            kwargs["enum_field_as_literal"] = LiteralType.All
        if self.reserved_field_names:
            kwargs["aliases"] = {name: f"{name}_" for name in sorted(self.reserved_field_names)}
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

    def apply(self, openapi: Mapping[str, object]) -> dict[str, object]:
        """Return a copy of the definition with `customTypePath` set on the nodes which get a custom type."""
        result = copy.deepcopy(dict(openapi))
        self._walk(result, component_schemas(result))
        return result

    def apply_to_file(self, openapi_file: Path, output_file: Path) -> None:
        """Write the definition read from `openapi_file` with custom types applied (see `apply`) to `output_file`."""
        output_file.write_text(json.dumps(self.apply(json.loads(openapi_file.read_text()))))

    def _walk(self, node: object, components: Mapping[str, object], *, in_union: bool = False) -> None:
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

    def _resolve_name(self, node: Mapping[str, object], components: Mapping[str, object]) -> str | None:
        if self.extension is not None and isinstance(name := node.get(self.extension), str):
            return name

        if self.extension is not None:
            target = referenced_component(node, components)
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
    """A field of a generated model - the same view of fields of msgspec structs and dataclasses (see `model_fields`)."""

    name: str
    type: object
    """Annotation of the field."""
    default: object
    """Default value of the field, `msgspec.NODEFAULT` for required fields and fields with `default_factory`."""
    default_factory: Callable[[], object] | None = None
    """Factory of default values of the field (e.g. `list` for `[]`), None for fields without it."""


def is_model(potential_model: object) -> bool:
    """Check whether the given object is a generated model class (msgspec struct or dataclass)."""
    if not isinstance(potential_model, type):
        return False
    return issubclass(potential_model, Struct) or dataclasses.is_dataclass(potential_model)


def is_model_class(node: ast.ClassDef) -> bool:
    """
    Check whether the class definition of a generated module is a model.

    Generated models are dataclasses (`@dataclass`, also without a base class) and classes deriving from a base class
    (msgspec structs, custom base classes).
    """
    return bool(node.bases) or any(_is_dataclass_decorator(decorator) for decorator in node.decorator_list)


def _is_dataclass_decorator(decorator: ast.expr) -> bool:
    target = decorator.func if isinstance(decorator, ast.Call) else decorator
    if isinstance(target, ast.Attribute):
        return target.attr == "dataclass"
    return isinstance(target, ast.Name) and target.id == "dataclass"


def model_fields(model: type[object]) -> list[ModelField]:
    """Fields of a model in declaration order (see `ModelField`)."""
    if issubclass(model, Struct):
        return [
            ModelField(
                field_.name,
                field_.type,
                field_.default,
                None if field_.default_factory is NODEFAULT else field_.default_factory,
            )
            for field_ in struct_fields(model)
        ]
    if not dataclasses.is_dataclass(model):
        raise TypeError(f"{model.__name__} is neither a msgspec struct nor a dataclass")

    from typing import get_type_hints

    hints = get_type_hints(model)
    result: list[ModelField] = []
    for field_ in dataclasses.fields(model):
        default = NODEFAULT if field_.default is dataclasses.MISSING else field_.default
        default_factory = None if field_.default_factory is dataclasses.MISSING else field_.default_factory
        result.append(ModelField(field_.name, hints[field_.name], default, default_factory))
    return result
