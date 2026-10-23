from __future__ import annotations

import ast
import builtins
import re
import tempfile
from pathlib import Path
from typing import Final

from datamodel_code_generator import generate

from api_client_generator._private.format_using_ruff import format_using_ruff
from api_client_generator._private.resolve_needed_imports import (
    compute_full_module_name,
    find_package_root,
)
from api_client_generator.exceptions import UndefinedModelError
from api_client_generator.model_options import CustomTypes, ModelOptions

_DEFAULT_MODEL_OPTIONS: Final[ModelOptions] = ModelOptions()


def generate_types_from_swagger(
    openapi_api_definition: str | Path,
    output: str | Path,
    *,
    model_options: ModelOptions | None = None,
    custom_types: CustomTypes | None = None,
) -> None:
    """
    Generate types defined in Swagger.

    Args:
        openapi_api_definition: The OpenAPI JSON definition file path.
        output: The output file / package path where the generated types will be saved.
        model_options: Shape of the generated models (model type, base class, ...). Defaults to plain msgspec structs.
        custom_types: Custom types replacing OpenAPI types of annotated schema nodes.

    Notes:
        The generated types will be saved in the specified output directory, and relative imports will be fixed
        to use absolute imports based on the package structure.

    Raises:
        FileNotFoundError: If the OpenAPI definition file does not exist.
    """
    openapi_file = openapi_api_definition if isinstance(openapi_api_definition, Path) else Path(openapi_api_definition)
    output = output if isinstance(output, Path) else Path(output)

    if not openapi_file.exists():
        raise FileNotFoundError(f"File {openapi_file} does not exist.")

    model_options = model_options or _DEFAULT_MODEL_OPTIONS
    _generate(openapi_file, output, model_options, custom_types)

    package_root = find_package_root(output)
    path_to_add_to_imports = compute_full_module_name(output, package_root)

    if path_to_add_to_imports.startswith(
        "."
    ):  # There is just one dot which means that output is in the same directory as package root
        path_to_add_to_imports = path_to_add_to_imports.replace(".", "", 1)

    fix_relative_imports(output, path_to_add_to_imports)
    if model_options.model_type == "dataclass":
        fix_dataclass_field_import(output)
    _format(output)


def _generate(
    openapi_file: Path,
    output: Path,
    model_options: ModelOptions,
    custom_types: CustomTypes | None,
) -> None:
    """Run datamodel-code-generator, applying custom types on a temporary copy of the definition if needed."""
    if custom_types is None:
        generate(openapi_file, output=output, **model_options.generate_kwargs())
        return

    with tempfile.TemporaryDirectory() as directory:
        # the copy has the name of the given definition - generated modules name it in their header
        tmp_spec = Path(directory) / openapi_file.name
        custom_types.apply_to_file(openapi_file, tmp_spec)
        generate(tmp_spec, output=output, **model_options.generate_kwargs())


def _format(output: Path) -> None:
    """Format generated files with ruff (datamodel-code-generator formatters are disabled, see `ModelOptions`)."""
    for py_file in [output] if output.is_file() else output.rglob("*.py"):
        py_file.write_text(format_using_ruff(py_file.read_text(encoding="utf-8")), encoding="utf-8")


def fix_dataclass_field_import(output: Path) -> None:
    """
    Import `dataclasses.field` in generated files which use it but do not import it.

    The dataclass template (see `model_options.TEMPLATES_DIRECTORY`) renders `field(metadata=...)` for renamed fields,
    while datamodel-code-generator collects imports before rendering, so it may miss `field`.

    Args:
        output: Output file path or directory containing generated files.
    """
    files_to_fix = [output] if output.is_file() else list(output.rglob("*.py"))

    for py_file in files_to_fix:
        content = py_file.read_text(encoding="utf-8")
        tree = ast.parse(content)
        uses_field = any(
            isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "field"
            for node in ast.walk(tree)
        )
        if not uses_field or "field" in _defined_names(tree):
            continue

        lines = content.split("\n")
        dataclasses_import = next(
            (
                node
                for node in tree.body
                if isinstance(node, ast.ImportFrom) and node.module == "dataclasses" and node.level == 0
            ),
            None,
        )
        if dataclasses_import is None:
            raise ValueError(f"{py_file}: uses dataclasses.field, but does not import from dataclasses")
        dataclasses_import.names.append(ast.alias(name="field"))
        start, end = dataclasses_import.lineno - 1, dataclasses_import.end_lineno or dataclasses_import.lineno
        lines[start:end] = [ast.unparse(dataclasses_import)]
        py_file.write_text("\n".join(lines), encoding="utf-8")


def check_references(module: Path) -> None:
    """
    Check that the generated module defines (or imports) everything its code refers to.

    Args:
        module: The generated module.

    Raises:
        UndefinedModelError: If the module refers to a model which it does not define.
    """
    tree = ast.parse(module.read_text(encoding="utf-8"))
    referenced = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load)}
    undefined = referenced - _defined_names(tree) - set(dir(builtins))
    if undefined:
        raise UndefinedModelError(module, undefined)


def _defined_names(module: ast.Module) -> set[str]:
    """Names defined at the top level of the module - classes, assignments and imports."""
    names: set[str] = set()
    for node in module.body:
        if isinstance(node, ast.ClassDef):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            names.update(target.id for target in node.targets if isinstance(target, ast.Name))
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
        elif isinstance(node, ast.Import | ast.ImportFrom):
            names.update((alias.asname or alias.name).partition(".")[0] for alias in node.names)
    return names


def fix_relative_imports(output_dir: Path, path_to_add: str) -> None:
    """
    Replace relative imports (from .xyz import ...) with absolute imports using the path_to_add.

    Args:
        output_dir: Directory with generated Python files.
        path_to_add: Path to use in absolute imports.
    """
    for py_file in output_dir.rglob("*.py"):
        content = py_file.read_text(encoding="utf-8")

        fixed_content = re.sub(
            r"^from \.(\w+) import (.+)$", rf"from {path_to_add}.\1 import \2", content, flags=re.MULTILINE
        )

        py_file.write_text(fixed_content, encoding="utf-8")
