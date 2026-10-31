from __future__ import annotations

import ast
import dataclasses
import sys
import warnings
from pathlib import Path
from typing import TYPE_CHECKING, Literal, get_type_hints

import datamodel_code_generator
import msgspec
import pytest

from api_client_generator._private.client_class_factory.common import create_api_client
from api_client_generator._private.common.array_handle import format_annotation, uses_literal
from api_client_generator._private.endpoints_factory import create_json_rpc_endpoint
from api_client_generator._private.endpoints_factory.json_rpc import get_endpoint_args
from api_client_generator._private.format_using_ruff import format_using_ruff
from api_client_generator.exceptions import EndpointParamsWithDefaultFactoryError, UnknownCustomTypeError
from api_client_generator.json_rpc import generate_api_client
from api_client_generator.model_options import (
    ALIAS_METADATA_KEY,
    TEMPLATES_DIRECTORY,
    CustomTypes,
    ModelOptions,
    ModelType,
    is_model,
    model_fields,
)

from .helpers import (
    annotation,
    classes,
    definition,
    field_assignment,
    generate_description,
    generate_models,
    import_module,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

OPENAPI = definition(
    {
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
    },
    {
        "test_api.get_account": ("get_account", "get_account_response"),
        "test_api.get_names": ("get_account", "get_names_response"),
    },
)

TYPES = {
    "Name": "my_types.Name",
    "BigInt": "my_types.BigInt",
    "Time": "my_types.Time",
    "Id": "my_types.Id",
}


def custom_types(*, types: Mapping[str, str] = TYPES, skip_in_unions: bool = False) -> CustomTypes:
    return CustomTypes(
        types=types, extension="x-test-type", format_types={"date-time": "Time"}, skip_in_unions=skip_in_unions
    )


def json_object(document: object, *path: str | int) -> dict[str, object]:
    """JSON object found in the document by keys of objects and indexes of arrays."""
    node = document
    for key in path:
        if isinstance(key, int) and isinstance(node, list):
            node = node[key]
            continue
        if isinstance(key, str) and isinstance(node, dict):
            node = node[key]
            continue
        raise TypeError(f"{key!r} cannot be taken from {node!r}")
    assert isinstance(node, dict), f"{'/'.join(map(str, path))}: not an object"
    return node


def generate(tmp_path: Path, model_options: ModelOptions, types: CustomTypes | None) -> str:
    return generate_description(
        tmp_path, OPENAPI, allow_passing_item_suffix=False, model_options=model_options, custom_types=types
    ).read_text()


def test_custom_types_are_applied_by_extension_ref_and_format() -> None:
    # ACT
    applied = custom_types().apply(OPENAPI)

    # ASSERT
    response = json_object(applied, "components", "schemas", "get_account_response", "properties")
    assert json_object(response, "name")["customTypePath"] == "my_types.Name"
    assert json_object(response, "balance")["customTypePath"] == "my_types.BigInt"  # from the referenced component
    assert json_object(response, "created")["customTypePath"] == "my_types.Time"  # from format
    assert "customTypePath" not in json_object(response, "comment")
    original = json_object(OPENAPI, "components", "schemas", "get_account_response", "properties", "name")
    assert "customTypePath" not in original


def test_custom_types_can_be_skipped_in_unions() -> None:
    # ACT
    applied = custom_types(skip_in_unions=True).apply(OPENAPI)
    applied_in_unions = custom_types().apply(OPENAPI)

    # ASSERT
    union = "get_account_response/properties/id_or_object"
    path = ("components", "schemas", "get_account_response", "properties", "id_or_object", "oneOf", 0)
    assert "customTypePath" not in json_object(applied, *path), union
    assert json_object(applied_in_unions, *path)["customTypePath"] == "my_types.Id"
    response = json_object(applied, "components", "schemas", "get_account_response", "properties")
    assert json_object(response, "name")["customTypePath"] == "my_types.Name", "outside unions types are applied"
    assert json_object(response, "balance")["customTypePath"] == "my_types.BigInt"


def test_custom_types_are_applied_in_nullable_unions_skipped_in_unions() -> None:
    # ARRANGE
    openapi = {
        "components": {
            "schemas": {
                "account": {
                    "type": "object",
                    "properties": {"name": {"anyOf": [{"type": "null"}, {"type": "string", "x-test-type": "Name"}]}},
                }
            }
        }
    }

    # ACT
    applied = custom_types(skip_in_unions=True).apply(openapi)

    # ASSERT
    name = json_object(applied, "components", "schemas", "account", "properties", "name", "anyOf", 1)
    assert name["customTypePath"] == "my_types.Name", "a nullable union is not a union of custom and other types"


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


def test_frozen_msgspec_models_are_refused() -> None:
    # ACT & ASSERT
    with pytest.raises(ValueError, match="only for dataclasses"):
        ModelOptions(model_type="msgspec", frozen=True)


@pytest.mark.parametrize(
    ("model_type", "base_class", "expected"),
    [
        ("msgspec", None, "Struct"),
        ("dataclass", None, "object"),
        ("msgspec", "pkg.base.Model", "Model"),
        ("dataclass", "pkg.base.Model", "Model"),
    ],
)
def test_base_class_name_is_the_last_part_of_its_path_or_the_default_base(
    model_type: ModelType, base_class: str | None, expected: str
) -> None:
    # ACT & ASSERT
    assert ModelOptions(model_type=model_type, base_class=base_class).base_class_name == expected


def test_model_helpers_support_structs_and_dataclasses() -> None:
    # ARRANGE
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


def test_params_with_defaults_created_by_factories_are_refused() -> None:
    # ARRANGE
    class StructParams(msgspec.Struct):
        names: list[str] = msgspec.field(default_factory=list)

    @dataclasses.dataclass
    class DataclassParams:
        names: list[str] = dataclasses.field(default_factory=list)

    # ACT & ASSERT
    for params in (StructParams, DataclassParams):
        assert [field_.default_factory for field_ in model_fields(params)] == [list]
        with pytest.raises(EndpointParamsWithDefaultFactoryError, match="names"):
            get_endpoint_args(params)


def test_client_class_attributes_are_emitted() -> None:
    # ACT
    class_def = create_api_client(
        "test_api",
        {},
        create_json_rpc_endpoint,
        "BaseApi",
        "endpoint",
        class_attributes={"__validation_module__": "pkg._validation.test_api", "__serialization__": "legacy"},
    )

    # ASSERT
    source = ast.unparse(ast.fix_missing_locations(ast.Module(body=[class_def], type_ignores=[])))
    assert "    __validation_module__ = 'pkg._validation.test_api'\n    __serialization__ = 'legacy'\n" in source
    assert ast.get_docstring(class_def) == "Client of the `test_api` API."


ALIASED_DESCRIPTION: str = """
from __future__ import annotations

from typing import TypeAlias

from msgspec import Struct

Uint64t: TypeAlias = int | str
AccountNames: TypeAlias = list[list[str]]


class Account(Struct):
    name: str


GetAccountCountResponse: TypeAlias = Uint64t
MaybeAccount: TypeAlias = Account | None

test_api_description = {
    "test_api": {
        "get_account_count": {"params": AccountNames, "result": GetAccountCountResponse},
        "find_accounts": {"params": AccountNames, "result": MaybeAccount, "response_array": True},
        "get_account": {"params": None, "result": Account},
    }
}
"""


def client_methods(client: Path) -> dict[str, ast.AsyncFunctionDef]:
    return {
        node.name: node for node in ast.walk(ast.parse(client.read_text())) if isinstance(node, ast.AsyncFunctionDef)
    }


def returns(method: ast.AsyncFunctionDef) -> str:
    assert method.returns is not None, f"{method.name} has no return annotation"
    return ast.unparse(method.returns)


def test_clients_refer_to_aliases_of_descriptions_by_their_names(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # ARRANGE
    description_file = tmp_path / "aliased_description.py"
    description_file.write_text(ALIASED_DESCRIPTION)
    description = import_module(description_file, monkeypatch)
    client = tmp_path / "test_api_client.py"

    # ACT
    generate_api_client(description.test_api_description, "BaseApi", "my_base", path=client)

    # ASSERT
    methods = client_methods(client)
    assert returns(methods["get_account_count"]) == "GetAccountCountResponse"
    assert ast.unparse(methods["get_account_count"].args.posonlyargs[1]) == "array_param: AccountNames"
    assert returns(methods["find_accounts"]) == "list[MaybeAccount]"
    assert returns(methods["get_account"]) == "Account"
    imported = {
        (node.module, alias.name)
        for node in ast.parse(client.read_text()).body
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
    }
    assert {
        (description.__name__, name) for name in ("GetAccountCountResponse", "AccountNames", "MaybeAccount", "Account")
    } <= imported


def test_clients_refer_to_aliases_of_descriptions_by_their_names_in_the_given_module(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # ARRANGE
    description_file = tmp_path / "aliased_description.py"
    description_file.write_text(ALIASED_DESCRIPTION)
    description = import_module(description_file, monkeypatch)
    monkeypatch.delitem(sys.modules, description.__name__)  # not found among imported modules
    client = tmp_path / "test_api_client.py"

    # ACT
    generate_api_client(
        description.test_api_description, "BaseApi", "my_base", path=client, description_module=description
    )

    # ASSERT
    methods = client_methods(client)
    assert returns(methods["get_account_count"]) == "GetAccountCountResponse"
    assert ast.unparse(methods["get_account_count"].args.posonlyargs[1]) == "array_param: AccountNames"


def test_clients_of_descriptions_without_module_refer_to_aliased_annotations(tmp_path: Path) -> None:
    # ARRANGE
    class Account(msgspec.Struct):
        name: str

    client = tmp_path / "test_api_client.py"
    description: dict[str, dict[str, dict[str, object]]] = {
        "test_api": {
            "find_accounts": {"params": list[list[str]], "result": Account | None, "response_array": True},
            "get_account": {"params": None, "result": Account | None},
        }
    }

    # ACT
    generate_api_client(description, "BaseApi", "my_base", path=client)

    # ASSERT
    methods = client_methods(client)
    assert returns(methods["find_accounts"]) == "list[Account | None]"
    assert ast.unparse(methods["find_accounts"].args.posonlyargs[1]) == "array_param: list[list[str]]"
    assert returns(methods["get_account"]) == "Account | None"


def test_enums_as_literals(tmp_path: Path) -> None:
    # ARRANGE
    status = {
        "type": "object",
        "properties": {"state": {"type": "string", "enum": ["on", "off"]}},
        "required": ["state"],
    }

    # ACT
    output = generate_models(
        tmp_path, definition({"status": status}), ModelOptions(model_type="dataclass", enum_as_literal=True)
    )

    # ASSERT
    source = output.read_text()
    assert "Literal['on', 'off']" in source or 'Literal["on", "off"]' in source
    assert "Enum" not in source


def test_literal_annotations_of_array_params() -> None:
    # ARRANGE
    annotation = list[list[str | Literal["incoming", "outgoing"]]]

    # ACT & ASSERT
    assert format_annotation(annotation) == "list[list[str | Literal['incoming', 'outgoing']]]"
    assert uses_literal(annotation)
    assert not uses_literal(list[str])


def test_dataclass_fields_keep_original_keys_in_metadata(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # ARRANGE
    records = {
        "type": "object",
        "properties": {
            "from": {"type": "string"},
            "Block stats": {"type": "integer"},
            "last-names": {"type": "array", "items": {"type": "string"}, "default": []},
            "limit": {"type": "integer", "default": 5},
            "name": {"type": "string"},
        },
        "required": ["from"],
    }

    # ACT
    output = generate_models(
        tmp_path, definition({"records": records}), ModelOptions(model_type="dataclass", frozen=True, kw_only=True)
    )

    # ASSERT
    module = import_module(output, monkeypatch)
    records_model = module.Records
    assert isinstance(records_model, type)
    assert dataclasses.is_dataclass(records_model)
    get_type_hints(records_model, vars(module))
    fields = {field_.name: field_ for field_ in dataclasses.fields(records_model)}
    assert {name: dict(field_.metadata) for name, field_ in fields.items()} == {
        "from_": {ALIAS_METADATA_KEY: "from"},
        "Block_stats": {ALIAS_METADATA_KEY: "Block stats"},
        "last_names": {ALIAS_METADATA_KEY: "last-names"},
        "limit": {},
        "name": {},
    }
    assert fields["from_"].default is dataclasses.MISSING
    assert fields["Block_stats"].default is None
    assert fields["last_names"].default_factory() == []  # type: ignore[operator]
    assert fields["limit"].default == 5
    assert fields["name"].default is None


def test_msgspec_models_keep_original_keys_in_field_names(tmp_path: Path) -> None:
    # ACT
    source = generate(tmp_path, ModelOptions(model_type="msgspec", kw_only=True), None)

    # ASSERT
    assert "metadata" not in source
    from_ = field_assignment(classes(source)["GetAccountResponse"], "from_")
    assert from_.value is not None
    assert ast.unparse(from_.value) == "field(name='from')"


ACCOUNT_API = definition(
    {
        "get_account": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]},
        "get_account_response": {
            "type": "object",
            "properties": {"from": {"type": "string"}, "balance": {"type": "integer"}},
            "required": ["from"],
        },
        "unused_thing": {"type": "object", "properties": {"value": {"type": "string"}}},
    },
    {"test_api.get_account": ("get_account", "get_account_response")},
)


@pytest.mark.parametrize(
    "model_options",
    [
        ModelOptions(),
        ModelOptions(model_type="msgspec", base_class="msgspec.Struct", kw_only=True),
        ModelOptions(model_type="dataclass"),
        ModelOptions(model_type="dataclass", base_class="my_base.Model", kw_only=True),
    ],
    ids=["msgspec", "msgspec-base", "dataclass", "dataclass-base"],
)
@pytest.mark.parametrize(
    ("flatten", "deduplicate_models"),
    [(False, False), (True, False), (True, True)],
    ids=["not-flattened", "flattened", "deduplicated"],
)
def test_only_models_of_endpoints_are_generated(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    model_options: ModelOptions,
    flatten: bool,
    deduplicate_models: bool,
) -> None:
    # ACT
    output = generate_description(
        tmp_path, ACCOUNT_API, model_options=model_options, flatten=flatten, deduplicate_models=deduplicate_models
    )

    # ASSERT
    assert set(classes(output.read_text())) == {"GetAccount", "GetAccountResponse"}
    if model_options.base_class == "my_base.Model":
        return  # the base class cannot be imported
    response = import_module(output, monkeypatch).GetAccountResponse
    assert isinstance(response, type)
    assert is_model(response)
    assert [field_.name for field_ in model_fields(response)] == ["from_", "balance"]


def test_generated_models_are_formatted_with_ruff_only(tmp_path: Path) -> None:
    # ACT
    with warnings.catch_warnings():
        warnings.simplefilter("error", FutureWarning)  # datamodel-code-generator warns about its default formatters
        output = generate_models(tmp_path, ACCOUNT_API, ModelOptions(kw_only=True))

    # ASSERT
    source = output.read_text()
    assert source == format_using_ruff(source)


@pytest.mark.parametrize("model_type", ["msgspec", "dataclass"])
def test_reserved_field_names_are_renamed_and_keep_their_keys(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, model_type: ModelType
) -> None:
    # ARRANGE
    records = {
        "type": "object",
        "properties": {"json": {"type": "string"}, "name": {"type": "string"}},
        "required": ["json", "name"],
    }

    # ACT
    output = generate_models(
        tmp_path,
        definition({"records": records}),
        ModelOptions(model_type=model_type, reserved_field_names=frozenset({"json"})),
        name=f"{model_type}_models",
    )

    # ASSERT
    records_model = import_module(output, monkeypatch).Records
    assert [field_.name for field_ in model_fields(records_model)] == ["json_", "name"]
    if model_type == "dataclass":
        assert [dict(field_.metadata) for field_ in dataclasses.fields(records_model)] == [
            {ALIAS_METADATA_KEY: "json"},
            {},
        ]
    else:
        assert [field_.encode_name for field_ in msgspec.structs.fields(records_model)] == ["json", "name"]


def test_dataclasses_have_the_description_of_their_schema_or_a_generic_docstring(tmp_path: Path) -> None:
    # ARRANGE
    name = {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}
    schemas = {"described": {**name, "description": "A described record."}, "plain": name}

    # ACT
    output = generate_models(tmp_path, definition(schemas), ModelOptions(model_type="dataclass"))

    # ASSERT
    models = classes(output.read_text())
    assert ast.get_docstring(models["Described"]) == "A described record."
    assert ast.get_docstring(models["Plain"]) == "The Plain model."


def test_dataclass_template_is_the_template_of_datamodel_code_generator_with_aliases_in_metadata() -> None:
    """The copied template has to be updated with the template of datamodel-code-generator when it changes."""
    # ARRANGE
    upstream = Path(datamodel_code_generator.__file__).parent / "model" / "template" / "dataclass.jinja2"
    template = (TEMPLATES_DIRECTORY / "dataclass.jinja2").read_text()
    alias_branch_start = "    {%- if field.alias and field.alias != field.name %}\n"
    alias_branch_end = "    {%- endif %}\n    {%- elif field.field %}\n"  # fields without aliases follow
    generic_docstring = '{%- else %}\n    """The {{ class_name }} model."""\n'
    fields_start = "{%- for field in fields -%}"
    upstream_pass = (
        "{%- if not fields and not description %}\n    pass\n{%- endif %}\n"  # not needed with the docstring
    )

    # ACT
    without_header = template[template.index("-#}\n") + len("-#}\n") :].replace(generic_docstring, "", 1)
    without_header = without_header.replace(fields_start, upstream_pass + fields_start, 1)
    start = without_header.index(alias_branch_start)
    end = without_header.index(alias_branch_end, start) + len(alias_branch_end)
    reverted = without_header[:start] + "    {%- if field.field %}\n" + without_header[end:]

    # ASSERT
    assert reverted == upstream.read_text()
