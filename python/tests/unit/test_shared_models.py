from __future__ import annotations

import ast
import subprocess
import sys
from typing import TYPE_CHECKING, Final

import pytest

from api_client_generator.json_rpc import generate_api_descriptions
from api_client_generator.model_options import ModelOptions

from .helpers import classes, definition, write_definition

if TYPE_CHECKING:
    from pathlib import Path

APIS: Final[tuple[str, ...]] = ("first_api", "second_api", "third_api")
COMMON_IMPORT: Final[str] = "pkg.common"

MANABAR: Final[dict[str, object]] = {
    "type": "object",
    "properties": {"current_mana": {"type": "integer"}, "last_update_time": {"type": "integer"}},
    "required": ["current_mana", "last_update_time"],
}

OPENAPI: Final[dict[str, object]] = definition(
    {
        "get_account": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]},
        "manabar": MANABAR,
        "account": {
            "type": "object",
            "properties": {"name": {"type": "string"}, "voting_manabar": {"$ref": "#/components/schemas/manabar"}},
            "required": ["name", "voting_manabar"],
        },
        "get_account_response": {
            "type": "object",
            "properties": {"account": {"$ref": "#/components/schemas/account"}},
            "required": ["account"],
        },
        "get_manabar_response": {
            "type": "object",
            "properties": {"rc_manabar": {"$ref": "#/components/schemas/manabar"}},
            "required": ["rc_manabar"],
        },
        "names": {"type": "array", "items": {"type": "string"}},
    },
    {
        "first_api.get_account": ("get_account", "get_account_response"),
        "first_api.get_names": ("get_account", "names"),
        "second_api.get_account": ("get_account", "get_account_response"),
        "second_api.get_manabar": ("get_account", "get_manabar_response"),
        "third_api.get_names": ("get_account", "names"),
    },
)


def generate(tmp_path: Path, model_options: ModelOptions | None = None) -> dict[str, str]:
    return generate_api_descriptions(
        write_definition(tmp_path, OPENAPI),
        {api: tmp_path / "pkg" / f"{api}.py" for api in APIS},
        tmp_path / "pkg" / "common",
        COMMON_IMPORT,
        allow_passing_item_suffix=False,
        model_options=model_options,
    )


def exports(module: Path) -> list[str]:
    for node in ast.parse(module.read_text()).body:
        if isinstance(node, ast.Assign) and ast.unparse(node.targets[0]) == "__all__":
            names = ast.literal_eval(node.value)
            assert isinstance(names, list)
            return names
    raise AssertionError(f"{module} has no `__all__`")


def aliases(module: Path) -> dict[str, str]:
    return {
        ast.unparse(node.target): ast.unparse(node.value)
        for node in ast.parse(module.read_text()).body
        if isinstance(node, ast.AnnAssign) and node.value is not None and ast.unparse(node.annotation) == "TypeAlias"
    }


def test_models_used_by_several_apis_are_moved_to_modules_of_the_common_package(tmp_path: Path) -> None:
    # ACT
    shared = generate(tmp_path)

    # ASSERT
    assert shared == {
        "Account": "account",
        "GetAccount": "get_account",
        "GetAccountResponse": "get_account_response",
        "Manabar": "manabar",
    }
    common = tmp_path / "pkg" / "common"
    assert sorted(path.name for path in common.iterdir()) == [f"{module}.py" for module in sorted(shared.values())]
    for name, module in shared.items():
        assert set(classes((common / f"{module}.py").read_text())) == {name}
    # models of the common package import the shared models they refer to
    assert "from pkg.common.manabar import Manabar\n" in (common / "account.py").read_text()
    assert "pkg.common" not in (common / "manabar.py").read_text()


def test_descriptions_alias_the_shared_models_and_keep_the_others(tmp_path: Path) -> None:
    # ACT
    generate(tmp_path)

    # ASSERT
    first, second, third = (tmp_path / "pkg" / f"{api}.py" for api in APIS)
    assert set(classes(first.read_text())) == set()
    assert set(classes(second.read_text())) == {"GetManabarResponse"}
    assert set(classes(third.read_text())) == set()
    # type aliases (of results) are not shared
    assert aliases(first) == {
        "Names": "list[str]",
        "Account": "common.Account",
        "GetAccount": "common.GetAccount",
        "GetAccountResponse": "common.GetAccountResponse",
        "Manabar": "common.Manabar",
    }
    assert aliases(third) == {"Names": "list[str]", "GetAccount": "common.GetAccount"}
    assert exports(second) == ["Account", "GetAccount", "GetAccountResponse", "GetManabarResponse", "Manabar"]
    assert exports(third) == ["GetAccount", "Names"]


@pytest.mark.parametrize(
    "model_options",
    [ModelOptions(), ModelOptions(model_type="dataclass")],
    ids=["msgspec", "dataclass-without-base-class"],
)
def test_apis_use_the_same_shared_models(tmp_path: Path, model_options: ModelOptions) -> None:
    # ARRANGE
    shared = generate(tmp_path, model_options)
    (tmp_path / "pkg" / "common" / "__init__.py").write_text(
        "".join(f"from pkg.common.{module} import {name}\n" for name, module in shared.items())
    )
    code = (
        "from pkg import common, first_api, second_api\n"
        "description = first_api.first_api_description['first_api']['get_account']\n"
        "print(first_api.Account is second_api.Account is common.Account, description['result'] is common."
        "GetAccountResponse, second_api.GetManabarResponse.__annotations__['rc_manabar'])\n"
    )

    # ACT
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True, cwd=tmp_path)

    # ASSERT
    assert result.stdout.split() == ["True", "True", "Manabar"]


def test_apis_without_endpoints_in_the_definition_are_refused(tmp_path: Path) -> None:
    # ACT & ASSERT
    with pytest.raises(ValueError, match="no endpoints of `fourth_api`"):
        generate_api_descriptions(
            write_definition(tmp_path, OPENAPI),
            {"fourth_api": tmp_path / "pkg" / "fourth_api.py"},
            tmp_path / "pkg" / "common",
            COMMON_IMPORT,
        )
