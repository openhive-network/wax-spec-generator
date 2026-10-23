"""
Models of several APIs shared in a common package - see `generate_api_descriptions`.

Models of all APIs are generated into one module, so a model used by several APIs (directly or by other models) is one
model - it is moved from description modules of the APIs to the common package:

- the common package holds a module per model, named after the model in snake case (`VotingManabar` -
  `voting_manabar.py`; a module named exactly as its model would replace the model as the attribute of the package once
  imported), with imports of the generated module and of the shared models the model refers to,
- description modules make the shared models they use their members again - aliases of the models of the common
  package (`VotingManabar: TypeAlias = common.VotingManabar`), so every API offers the complete set of its models,
- description modules export their models and type aliases (`__all__`).

Only models are shared - type aliases (e.g. of results of endpoints) stay in every module using them. Models of the
flattened and deduplicated definition refer only to other models (schemas of other kinds are inlined).
"""

from __future__ import annotations

import ast
from collections import Counter
from typing import TYPE_CHECKING, Final

from api_client_generator._private.common.converters import camel_to_snake
from api_client_generator.json_rpc.clean_openapi import definition_lines, parse_models_and_aliases
from api_client_generator.model_options import is_model_class

if TYPE_CHECKING:
    from collections.abc import Collection, Mapping
    from pathlib import Path

SHARED_MODELS_COMMENT: Final[str] = (
    "# models shared with other APIs (the common package) - members of this API as all its models\n"
)


def share_models(
    models: str, description_files: Collection[Path], common_package: Path, common_import: str
) -> dict[str, str]:
    """
    Move models used by several of the description modules to the common package.

    Args:
        models: The generated module holding models of all APIs (the source of the description modules).
        description_files: Description modules - the generated module without models unused by their APIs.
        common_package: Directory of the common package (created when a model is shared, without `__init__.py`).
        common_import: Import path of the common package.

    Returns:
        Modules of the common package (names in the package) by names of the shared models.

    Raises:
        ValueError: If names of two shared models are the same in snake case.
    """
    usage = Counter(name for path in description_files for name in _model_classes(ast.parse(path.read_text())))
    modules = {name: camel_to_snake(name) for name, count in sorted(usage.items()) if count > 1}
    if len(set(modules.values())) != len(modules):
        raise ValueError("Models with the same name in snake case cannot be shared in modules of the common package.")

    for path in description_files:
        _use_shared_models(path, modules.keys(), common_import)
    if modules:
        common_package.mkdir(parents=True, exist_ok=True)
        for name, source in _common_modules(models, modules, common_import).items():
            (common_package / f"{modules[name]}.py").write_text(source, encoding="utf-8")
    return modules


def _model_classes(module: ast.Module) -> dict[str, ast.ClassDef]:
    return {node.name: node for node in module.body if isinstance(node, ast.ClassDef) and is_model_class(node)}


def _use_shared_models(path: Path, shared: Collection[str], common_import: str) -> None:
    """Replace the shared models of the description module by aliases of the models of the common package."""
    source = path.read_text(encoding="utf-8")
    lines = source.splitlines(keepends=True)
    module = ast.parse(source)
    classes = _model_classes(module)
    used = sorted(name for name in classes if name in shared)
    removed = {number for name in used for number in definition_lines(classes[name])}
    aliases = {
        node.target.id
        for node in module.body
        if isinstance(node, ast.AnnAssign)
        and isinstance(node.target, ast.Name)
        and ast.unparse(node.annotation) == "TypeAlias"
    }
    exported = sorted(name for name in classes.keys() | aliases if not name.startswith("_"))

    package, _, common = common_import.rpartition(".")
    inserted = [f"from {package} import {common}\n", "from typing import TypeAlias\n"] if used else []
    inserted += ["\n__all__ = [\n", *(f'    "{name}",\n' for name in exported), "]\n"]
    if used:
        inserted += ["\n", SHARED_MODELS_COMMENT, *(f"{name}: TypeAlias = {common}.{name}\n" for name in used)]

    end_of_imports = max(
        (node.end_lineno or node.lineno for node in module.body if isinstance(node, ast.Import | ast.ImportFrom)),
        default=0,
    )
    kept = [line for number, line in enumerate(lines, start=1) if number > end_of_imports and number not in removed]
    path.write_text("".join([*lines[:end_of_imports], *inserted, *kept]), encoding="utf-8")


def _common_modules(models: str, modules: Mapping[str, str], common_import: str) -> dict[str, str]:
    """Sources of modules of the shared models - imports of the generated module, then the model."""
    lines = models.splitlines(keepends=True)
    module = ast.parse(models)
    imports = [
        "".join(lines[node.lineno - 1 : node.end_lineno or node.lineno])
        for node in module.body
        if isinstance(node, ast.Import | ast.ImportFrom)
        and not (isinstance(node, ast.ImportFrom) and node.module == "__future__")
    ]
    classes = _model_classes(module)
    dependencies = parse_models_and_aliases(models)
    return {
        name: "".join(
            [
                "from __future__ import annotations\n\n",
                *imports,
                *(
                    f"from {common_import}.{modules[reference]} import {reference}\n"
                    for reference in sorted(dependencies[name] & modules.keys())
                ),
                "\n\n",
                *(lines[number - 1] for number in definition_lines(classes[name])),
            ]
        )
        for name in modules
    }
