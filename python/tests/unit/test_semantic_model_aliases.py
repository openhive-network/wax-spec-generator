from __future__ import annotations

import ast
import textwrap
from pathlib import Path

from api_client_generator.semantic_model_aliases import SemanticModelAlias, apply_semantic_model_aliases


def test_semantic_model_aliases_collapse_equivalent_models(tmp_path: Path) -> None:
    description = tmp_path / "api_description.py"
    description.write_text(
        textwrap.dedent(
            """
            from __future__ import annotations

            from typing import Any, TypeAlias

            from msgspec import UNSET, Struct, UnsetType

            class Extension(Struct):
                type: str
                value: dict[str, Any]

            class Operation(Struct):
                type: str
                value: dict[str, Any]

            class Transaction3(Struct):
                ref_block_num: int
                ref_block_prefix: int
                expiration: str
                extensions: list[Extension]
                signatures: list[str]
                operations: list[Operation]

            class Block(Struct):
                transactions: list[Transaction3]

            class Transaction4(Struct):
                ref_block_num: int
                ref_block_prefix: int
                expiration: str
                extensions: list[Extension]
                signatures: list[str]
                operations: list[Operation]

            class Block1(Struct):
                transactions: list[Transaction4]

            class GetBlockResponse(Struct):
                block: Block1 | UnsetType = UNSET

            block_api_description = {
                "block_api": {
                    "get_block": {
                        "params": object,
                        "result": GetBlockResponse,
                        "description": "",
                    },
                }
            }
            """
        ),
        encoding="utf-8",
    )

    apply_semantic_model_aliases(
        description,
        (
            SemanticModelAlias("Transaction", ("Transaction3", "Transaction4"), ("BlockTransaction",)),
            SemanticModelAlias("Block", ("Block", "Block1")),
            SemanticModelAlias("Operation", ("Operation",), ("OperationEnvelope",), minimum_members=1),
        ),
    )

    classes = _classes_from(description)
    aliases = _aliases_from(description)
    assert "Transaction" in classes
    assert "Block" in classes
    assert "Transaction3" not in classes
    assert "Transaction4" not in classes
    assert "Block1" not in classes
    assert aliases["Transaction3"] == "Transaction"
    assert aliases["Transaction4"] == "Transaction"
    assert aliases["BlockTransaction"] == "Transaction"
    assert aliases["Block1"] == "Block"
    assert aliases["OperationEnvelope"] == "Operation"
    assert _field_annotation(classes["Block"], "transactions") == "list[Transaction]"
    assert _field_annotation(classes["GetBlockResponse"], "block") == "Block | UnsetType"


def test_semantic_model_aliases_skip_non_equivalent_models(tmp_path: Path) -> None:
    description = tmp_path / "api_description.py"
    description.write_text(
        textwrap.dedent(
            """
            from __future__ import annotations

            from typing import TypeAlias

            from msgspec import Struct

            class Account(Struct):
                name: str

            class Account1(Struct):
                name: str
                proxy: str

            api_description = {}
            """
        ),
        encoding="utf-8",
    )

    apply_semantic_model_aliases(description, (SemanticModelAlias("Account", ("Account", "Account1")),))

    classes = _classes_from(description)
    assert "Account" in classes
    assert "Account1" in classes
    assert _aliases_from(description) == {}


def test_semantic_model_aliases_only_rewrite_code_identifiers(tmp_path: Path) -> None:
    description = tmp_path / "api_description.py"
    description.write_text(
        textwrap.dedent(
            '''
            from __future__ import annotations

            from msgspec import Struct

            class Balance(Struct):
                """Balance should stay in docstrings."""
                amount: str
                nai: str
                precision: int

            class HbdBalance(Struct):
                amount: str
                nai: str
                precision: int

            class Price(Struct):
                base: Balance
                quote: HbdBalance

            # Balance should stay in comments.
            api_description = {"description": "Balance should stay in strings", "result": Price}
            '''
        ),
        encoding="utf-8",
    )

    apply_semantic_model_aliases(description, (SemanticModelAlias("NaiAsset", ("Balance", "HbdBalance")),))

    content = description.read_text(encoding="utf-8")
    classes = _classes_from(description)
    aliases = _aliases_from(description)
    assert "NaiAsset" in classes
    assert "HbdBalance" not in classes
    assert aliases["Balance"] == "NaiAsset"
    assert aliases["HbdBalance"] == "NaiAsset"
    assert _field_annotation(classes["Price"], "base") == "NaiAsset"
    assert _field_annotation(classes["Price"], "quote") == "NaiAsset"
    assert "Balance should stay in docstrings." in content
    assert "Balance should stay in comments." in content
    assert "Balance should stay in strings" in content


def test_semantic_model_aliases_are_idempotent(tmp_path: Path) -> None:
    description = tmp_path / "api_description.py"
    description.write_text(
        textwrap.dedent(
            """
            from __future__ import annotations

            from msgspec import Struct

            class Balance(Struct):
                amount: str
                nai: str
                precision: int

            class HbdBalance(Struct):
                amount: str
                nai: str
                precision: int

            api_description = {}
            """
        ),
        encoding="utf-8",
    )
    groups = (SemanticModelAlias("NaiAsset", ("Balance", "HbdBalance")),)

    apply_semantic_model_aliases(description, groups)
    once = description.read_text(encoding="utf-8")
    apply_semantic_model_aliases(description, groups)

    assert description.read_text(encoding="utf-8") == once


def test_semantic_model_aliases_can_move_models_to_common_module(tmp_path: Path) -> None:
    description = tmp_path / "api_description.py"
    common = tmp_path / "common.py"
    description.write_text(
        textwrap.dedent(
            """
            from __future__ import annotations

            from typing import TypeAlias

            from msgspec import Struct

            class Balance(Struct):
                amount: str
                nai: str
                precision: int

            class HbdBalance(Struct):
                amount: str
                nai: str
                precision: int

            class SellPrice(Struct):
                base: Balance
                quote: HbdBalance

            class CurrentMedianHistory(Struct):
                base: Balance
                quote: HbdBalance

            class GetPriceResponse(Struct):
                price: CurrentMedianHistory

            api_description = {"result": CurrentMedianHistory}
            """
        ),
        encoding="utf-8",
    )

    apply_semantic_model_aliases(
        description,
        (
            SemanticModelAlias("NaiAsset", ("Balance", "HbdBalance")),
            SemanticModelAlias("PricePair", ("SellPrice", "CurrentMedianHistory")),
        ),
        common_file=common,
        common_import="generated_common",
    )

    description_content = description.read_text(encoding="utf-8")
    description_classes = _classes_from(description)
    common_classes = _classes_from(common)
    aliases = _aliases_from(description)

    assert "from generated_common import NaiAsset, PricePair" in description_content
    assert "NaiAsset" not in description_classes
    assert "PricePair" not in description_classes
    assert "Balance" not in description_classes
    assert "HbdBalance" not in description_classes
    assert "SellPrice" not in description_classes
    assert "CurrentMedianHistory" not in description_classes
    assert "NaiAsset" in common_classes
    assert "PricePair" in common_classes
    assert aliases["Balance"] == "NaiAsset"
    assert aliases["HbdBalance"] == "NaiAsset"
    assert aliases["SellPrice"] == "PricePair"
    assert aliases["CurrentMedianHistory"] == "PricePair"
    assert _field_annotation(description_classes["GetPriceResponse"], "price") == "PricePair"
    assert _field_annotation(common_classes["PricePair"], "base") == "NaiAsset"
    assert _field_annotation(common_classes["PricePair"], "quote") == "NaiAsset"


def test_semantic_model_aliases_reuse_existing_common_model(tmp_path: Path) -> None:
    first_description = tmp_path / "first_description.py"
    second_description = tmp_path / "second_description.py"
    common = tmp_path / "common.py"
    first_description.write_text(
        textwrap.dedent(
            """
            from __future__ import annotations

            from msgspec import Struct

            class Balance(Struct):
                amount: str
                nai: str
                precision: int

            class HbdBalance(Struct):
                amount: str
                nai: str
                precision: int

            api_description = {}
            """
        ),
        encoding="utf-8",
    )
    second_description.write_text(
        textwrap.dedent(
            """
            from __future__ import annotations

            from msgspec import Struct

            class SavingsBalance(Struct):
                amount: str
                nai: str
                precision: int

            class RewardHbdBalance(Struct):
                amount: str
                nai: str
                precision: int

            api_description = {}
            """
        ),
        encoding="utf-8",
    )

    apply_semantic_model_aliases(
        first_description,
        (SemanticModelAlias("NaiAsset", ("Balance", "HbdBalance")),),
        common_file=common,
        common_import="generated_common",
    )
    common_after_first_run = common.read_text(encoding="utf-8")
    apply_semantic_model_aliases(
        second_description,
        (SemanticModelAlias("NaiAsset", ("SavingsBalance", "RewardHbdBalance")),),
        common_file=common,
        common_import="generated_common",
    )

    assert common.read_text(encoding="utf-8") == common_after_first_run
    assert "from generated_common import NaiAsset" in second_description.read_text(encoding="utf-8")
    assert _aliases_from(second_description)["SavingsBalance"] == "NaiAsset"
    assert _aliases_from(second_description)["RewardHbdBalance"] == "NaiAsset"


def test_semantic_model_aliases_keep_local_model_when_common_dependencies_are_not_available(tmp_path: Path) -> None:
    description = tmp_path / "api_description.py"
    common = tmp_path / "common.py"
    description.write_text(
        textwrap.dedent(
            """
            from __future__ import annotations

            from msgspec import Struct

            class Extension(Struct):
                type: str

            class Transaction3(Struct):
                extensions: list[Extension]

            class Transaction4(Struct):
                extensions: list[Extension]

            api_description = {"result": Transaction4}
            """
        ),
        encoding="utf-8",
    )

    apply_semantic_model_aliases(
        description,
        (SemanticModelAlias("Transaction", ("Transaction3", "Transaction4")),),
        common_file=common,
        common_import="generated_common",
    )

    classes = _classes_from(description)
    aliases = _aliases_from(description)
    assert not common.exists()
    assert "Transaction" in classes
    assert "Transaction4" not in classes
    assert aliases["Transaction3"] == "Transaction"
    assert aliases["Transaction4"] == "Transaction"
    assert "from generated_common import" not in description.read_text(encoding="utf-8")


def _classes_from(path: Path) -> dict[str, ast.ClassDef]:
    return {
        node.name: node for node in ast.parse(path.read_text(encoding="utf-8")).body if isinstance(node, ast.ClassDef)
    }


def _aliases_from(path: Path) -> dict[str, str]:
    aliases: dict[str, str] = {}
    for node in ast.parse(path.read_text(encoding="utf-8")).body:
        if not isinstance(node, ast.AnnAssign):
            continue
        if not isinstance(node.target, ast.Name):
            continue
        if ast.unparse(node.annotation) != "TypeAlias" or node.value is None:
            continue
        aliases[node.target.id] = ast.unparse(node.value)
    return aliases


def _field_annotation(class_node: ast.ClassDef, field_name: str) -> str:
    for statement in class_node.body:
        if not isinstance(statement, ast.AnnAssign):
            continue
        if not isinstance(statement.target, ast.Name):
            continue
        if statement.target.id == field_name:
            return ast.unparse(statement.annotation)
    raise AssertionError(f"Field {field_name} was not found")
