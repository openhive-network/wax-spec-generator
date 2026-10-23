from __future__ import annotations

import ast
import textwrap
from typing import TYPE_CHECKING

import pytest

from api_client_generator.exceptions import UndefinedModelError
from api_client_generator.generate_types_from_swagger import check_references
from api_client_generator.json_rpc import append_endpoint_results
from api_client_generator.json_rpc.clean_openapi import clean_file
from api_client_generator.tidy import tidy_with_ruff

from .helpers import import_module

if TYPE_CHECKING:
    from pathlib import Path


def test_tidy_removes_unused_and_sorts_imports(tmp_path: Path) -> None:
    # ARRANGE
    module = tmp_path / "generated.py"
    module.write_text(
        textwrap.dedent(
            """
            from __future__ import annotations
            from typing import TypeAlias, Final
            from dataclasses import dataclass
            from os import path
            Alias: TypeAlias = dict[str, int]
            LIMIT: Final = 1
            @dataclass
            class Model:
                value: Alias
            """
        )
    )

    # ACT
    tidy_with_ruff(module)

    # ASSERT
    source = module.read_text()
    assert "from os import path" not in source
    assert source.index("from dataclasses import dataclass") < source.index("from typing import Final, TypeAlias")


def test_tidy_sorts_dunder_all_and_strips_trailing_whitespace_in_docstrings(tmp_path: Path) -> None:
    # ARRANGE
    module = tmp_path / "generated.py"
    module.write_text(
        'from __future__ import annotations\n\n__all__ = ["b", "a"]\n\na = 1\nb = 2\n\n\nclass Model:\n'
        '    """\n    Description from openapi.json   \n    """\n'
    )

    # ACT
    tidy_with_ruff(module)

    # ASSERT
    source = module.read_text()
    assert '__all__ = ["a", "b"]' in source
    assert "openapi.json\n" in source


def test_tidy_requires_ruff_of_the_generator(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # ARRANGE
    import subprocess

    import api_client_generator.tidy

    module = tmp_path / "generated.py"
    module.write_text("x = 1\n")
    commands: list[object] = []

    def ruff_not_installed() -> str:
        raise FileNotFoundError

    monkeypatch.setattr(api_client_generator.tidy, "find_ruff_bin", ruff_not_installed)
    monkeypatch.setattr(subprocess, "run", lambda command, **_: commands.append(command))

    # ACT & ASSERT
    with pytest.raises(FileNotFoundError, match="ruff installed with hiveio-api-client-generator"):
        tidy_with_ruff(module)
    assert commands == []


def test_endpoint_results_map_methods_to_result_models(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # ARRANGE
    module_file = tmp_path / "description.py"
    module_file.write_text(
        textwrap.dedent(
            """
            class Account:
                pass

            class Version:
                pass

            test_api_description = {
                "test_api": {
                    "find_accounts": {"params": None, "result": Account, "response_array": True},
                    "get_version": {"params": None, "result": Version},
                }
            }
            """
        )
    )

    # ACT
    append_endpoint_results(module_file, "test_api_description")

    # ASSERT
    assert "'get_version': (Version, False)," in module_file.read_text(), "models are written out (for type checkers)"
    module = import_module(module_file, monkeypatch)
    assert module.ENDPOINT_RESULTS == {
        "find_accounts": (module.Account, True),
        "get_version": (module.Version, False),
    }


def test_endpoint_results_are_replaced_and_endpoints_without_results_map_to_none(tmp_path: Path) -> None:
    # ARRANGE
    module_file = tmp_path / "description.py"
    module_file.write_text(
        'class Version:\n    pass\n\n\ntest_api_description = {"test_api": {"get_version": {"result": Version}}}\n'
    )
    append_endpoint_results(module_file, "test_api_description")
    first = module_file.read_text()
    module_file.write_text(
        first.replace('{"get_version": {"result": Version}}', '{"get_version": {"result": Version}, "stop": {}}')
    )

    # ACT
    append_endpoint_results(module_file, "test_api_description")

    # ASSERT
    namespace: dict[str, object] = {}
    exec(compile(module_file.read_text(), str(module_file), "exec"), namespace)  # noqa: S102
    assert namespace["ENDPOINT_RESULTS"] == {"get_version": (namespace["Version"], False), "stop": (None, False)}
    assert module_file.read_text().count("ENDPOINT_RESULTS") == 1


def test_endpoint_results_require_the_description(tmp_path: Path) -> None:
    # ARRANGE
    module_file = tmp_path / "description.py"
    module_file.write_text("other_description = {}\n")

    # ACT & ASSERT
    with pytest.raises(ValueError, match="test_api_description"):
        append_endpoint_results(module_file, "test_api_description")


def test_references_to_models_which_are_not_defined_raise(tmp_path: Path) -> None:
    # ARRANGE
    module = tmp_path / "description.py"
    module.write_text(
        textwrap.dedent(
            """
            from typing import TypeAlias
            from msgspec import Struct, field

            class Account(Struct):
                name: str = field(name="Name")
                balance: Balance

            Accounts: TypeAlias = list[Account]
            test_api_description = {"test_api": {"find_accounts": {"params": None, "result": Accounts}}}
            """
        )
    )

    # ACT & ASSERT
    with pytest.raises(UndefinedModelError, match="Balance") as error:
        check_references(module)
    assert error.value.names == ("Balance",)


def test_modules_defining_every_referenced_model_pass_the_check(tmp_path: Path) -> None:
    # ARRANGE
    module = tmp_path / "description.py"
    module.write_text(
        textwrap.dedent(
            """
            import msgspec
            from typing import TypeAlias

            class Balance(msgspec.Struct):
                amount: int | None = None

            class Account(msgspec.Struct):
                balance: Balance

            Accounts: TypeAlias = list[Account]
            """
        )
    )

    # ACT & ASSERT
    check_references(module)


def test_clean_file_keeps_used_definitions_intact(tmp_path: Path) -> None:
    # ARRANGE
    module = tmp_path / "description.py"
    module.write_text(
        textwrap.dedent(
            """
            from msgspec import UNSET, Struct, UnsetType

            class Peer(Struct):
                firewall_status: str | UnsetType = (
                    UNSET
                )

            Peers: TypeAlias = list[
                Peer
            ]
            """
        )
    )

    # ACT
    clean_file(module, {"Peers"})

    # ASSERT
    tree = ast.parse(module.read_text())
    peer = next(node for node in tree.body if isinstance(node, ast.ClassDef))
    field = peer.body[0]
    assert isinstance(field, ast.AnnAssign)
    assert field.value is not None
    assert ast.unparse(field.value) == "UNSET"
    alias = tree.body[-1]
    assert isinstance(alias, ast.AnnAssign)
    assert alias.value is not None
    assert ast.unparse(alias.value) == "list[Peer]"


def test_clean_file_removes_unused_models_with_decorators_and_aliases_with_docstrings(tmp_path: Path) -> None:
    # ARRANGE
    module = tmp_path / "description.py"
    module.write_text(
        textwrap.dedent(
            """
            from dataclasses import dataclass
            from typing import TypeAlias

            @dataclass(kw_only=True)
            class Unused:
                name: str

            Names: TypeAlias = list[str]
            \"\"\"
            Names of unused accounts.
            \"\"\"

            @dataclass
            class Account:
                \"\"\"
                Mentions Unused and Names in its documentation only.
                \"\"\"

                name: str

            Accounts: TypeAlias = list[Account]
            \"\"\"
            Accounts found.
            \"\"\"
            """
        )
    )

    # ACT
    clean_file(module, {"Accounts"})

    # ASSERT
    tree = ast.parse(module.read_text())
    assert [ast.unparse(node).splitlines()[0] for node in tree.body] == [
        "from dataclasses import dataclass",
        "from typing import TypeAlias",
        "@dataclass",
        "Accounts: TypeAlias = list[Account]",
        "'\\nAccounts found.\\n'",
    ]
    account = tree.body[2]
    assert isinstance(account, ast.ClassDef)
    assert [ast.unparse(decorator) for decorator in account.decorator_list] == ["dataclass"]
