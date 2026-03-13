from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any, Final

from datamodel_code_generator import DataModelType, InputFileType, PythonVersion, generate

from api_client_generator._private.common.converters import camel_to_snake
from api_client_generator._private.resolve_needed_imports import (
    compute_full_module_name,
    find_package_root,
)

_GENERATE_KWARGS: Final[dict[str, Any]] = {
    "output_model_type": DataModelType.MsgspecStruct,
    "input_file_type": InputFileType.OpenAPI,
    "use_field_description": True,
    "use_standard_collections": True,
    "use_exact_imports": True,
    "target_python_version": PythonVersion.PY_311,
}


def generate_types_from_swagger(
    openapi_api_definition: str | Path,
    output: str | Path,
) -> None:
    """
    Generate types defined in Swagger.

    Args:
        openapi_api_definition: The OpenAPI JSON definition file path.
        output: The output file / package path where the generated types will be saved.

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

    generate(  # generation of types available in the API definition
        openapi_file,
        output=output,
        **_GENERATE_KWARGS,
    )

    package_root = find_package_root(output)
    path_to_add_to_imports = compute_full_module_name(output, package_root)

    if path_to_add_to_imports.startswith(
        "."
    ):  # There is just one dot which means that output is in the same directory as package root
        path_to_add_to_imports = path_to_add_to_imports.replace(".", "", 1)

    fix_relative_imports(output, path_to_add_to_imports)
    fix_malformed_typealias(output)
    fix_forward_references(output)


def fix_malformed_typealias(output: Path) -> None:
    """
    Fix malformed TypeAlias declarations in generated files.

    datamodel-code-generator v0.52.2 has a bug where it can generate malformed
    TypeAlias declarations for certain recursive array types with oneOf, like:

    AccountHistoryArrayCondenserApi: TypeAlias = list[
        int | AccountHistoryArrayCondenserApi1

    This should be:

    AccountHistoryArrayCondenserApi: TypeAlias = list[int | AccountHistoryArrayCondenserApi1]

    This function fixes these malformed declarations by detecting incomplete list[]
    expressions and merging them with the following line.

    Args:
        output: Output file path or directory containing generated files.
    """
    files_to_fix = [output] if output.is_file() else list(output.rglob("*.py"))

    for py_file in files_to_fix:
        content = py_file.read_text(encoding="utf-8")
        lines = content.split("\n")
        fixed_lines = []
        i = 0

        while i < len(lines):
            line = lines[i]

            # Check if this line is a malformed TypeAlias with unclosed list[
            # Pattern: ends with "list[" or "list[\n    <type> |"
            if ": TypeAlias = list[" in line and not line.rstrip().endswith("]"):
                # Count open/close brackets
                open_brackets = line.count("[")
                close_brackets = line.count("]")

                if open_brackets > close_brackets:
                    # This line has unclosed brackets, need to merge with next lines
                    merged_line = line
                    i += 1

                    # Keep merging lines until brackets are balanced
                    while i < len(lines) and open_brackets > close_brackets:
                        next_line = lines[i].strip()
                        if next_line:
                            # Merge the content (remove leading spaces, keep the type expression)
                            if not merged_line.rstrip().endswith("["):
                                merged_line = merged_line.rstrip() + " " + next_line
                            else:
                                merged_line = merged_line.rstrip() + next_line
                        open_brackets += lines[i].count("[")
                        close_brackets += lines[i].count("]")
                        i += 1

                    # If still unclosed, add the missing bracket
                    if open_brackets > close_brackets:
                        merged_line = merged_line.rstrip() + "]"

                    # Clean up extra spaces before closing brackets
                    merged_line = re.sub(r"\s+\]", "]", merged_line)

                    fixed_lines.append(merged_line)
                    continue

            fixed_lines.append(line)
            i += 1

        fixed_content = "\n".join(fixed_lines)
        if fixed_content != content:
            py_file.write_text(fixed_content, encoding="utf-8")


def fix_forward_references(output: Path) -> None:
    """
    Remove TypeAlias definitions that reference undefined types.

    datamodel-code-generator sometimes generates references to types that don't exist
    (like AccountHistoryArray1). These cause NameError at import time. We remove them
    ONLY if they're not referenced in the API description dict (which appears at the
    end of the file).

    Args:
        output: Output file path or directory containing generated files.
    """
    files_to_fix = [output] if output.is_file() else list(output.rglob("*.py"))

    for py_file in files_to_fix:
        content = py_file.read_text(encoding="utf-8")

        # Extract all defined types (TypeAlias and class definitions)
        defined_types = set()
        typealias_lines = {}  # Map type name to line content for removal check
        for line_num, line in enumerate(content.split("\n")):
            # Match TypeAlias: SomeName: TypeAlias = ...
            if ": TypeAlias = " in line:
                match = re.match(r"^(\w+):\s*TypeAlias\s*=", line)
                if match:
                    type_name = match.group(1)
                    defined_types.add(type_name)
                    typealias_lines[type_name] = line_num
            # Match class definitions: class SomeName(...):
            elif line.startswith("class "):
                match = re.match(r"^class\s+(\w+)", line)
                if match:
                    defined_types.add(match.group(1))

        # Find types referenced in the API description dict (typically at the end)
        # Look for patterns like "params": SomeType, or "result": SomeType,
        referenced_in_description = set()
        for line in content.split("\n"):
            # Match description dict entries: "params": TypeName, or "result": TypeName,
            if '"params":' in line or '"result":' in line:
                # Extract the type name after the colon
                match = re.search(r":\s*([A-Z]\w+)\s*,", line)
                if match:
                    referenced_in_description.add(match.group(1))

        # Also add built-in types that should not be considered undefined
        builtin_types = {
            "int",
            "str",
            "float",
            "bool",
            "dict",
            "list",
            "tuple",
            "set",
            "Any",
            "None",
            "Union",
            "Optional",
            "Literal",
            "UNSET",
            "UnsetType",
            "Meta",
            "Struct",
            "field",
        }
        defined_types.update(builtin_types)

        # Remove TypeAlias lines with undefined references, BUT ONLY if they're not
        # referenced in the API description. For those that are used, create stub classes.
        lines = content.split("\n")
        fixed_lines = []
        undefined_types_to_stub = set()

        for line_num, line in enumerate(lines):
            if ": TypeAlias = " in line and not line.strip().endswith('"""'):
                # Extract the type expression after "= "
                match = re.match(r"^(\w+):\s*TypeAlias\s*=\s*(.+)$", line)
                if match:
                    type_name, type_expr = match.groups()

                    # Find all identifiers in the type expression
                    # Match word boundaries to get type names
                    identifiers = re.findall(r"\b([A-Z]\w+)\b", type_expr)

                    # Collect undefined types for stub creation
                    undefined_refs = [id for id in identifiers if id not in defined_types]

                    if undefined_refs:
                        if type_name in referenced_in_description:
                            # Type is used in API description but has undefined refs
                            # Mark undefined refs for stub creation
                            undefined_types_to_stub.update(undefined_refs)
                        else:
                            # Type is not used - remove it entirely
                            continue

            fixed_lines.append(line)

        # Insert stub class definitions for undefined types at the beginning
        # (after imports and blank lines)
        if undefined_types_to_stub:
            # Find the line after all imports and blank lines
            insert_index = 0
            in_import_section = False
            for i, line in enumerate(fixed_lines):
                if line.startswith("from ") or line.startswith("import "):
                    in_import_section = True
                    insert_index = i + 1
                elif in_import_section and line.strip() == "":
                    # Still in blank lines after imports
                    insert_index = i + 1
                elif in_import_section and line.strip() != "":
                    # Found first non-blank line after imports
                    break

            # Create stub classes
            stubs = ["# Stub classes for undefined types referenced by datamodel-code-generator"]
            for undefined_type in sorted(undefined_types_to_stub):
                stubs.append(f"class {undefined_type}(Struct):")
                stubs.append("    pass")
                stubs.append("")
            stubs.append("")  # Extra blank line

            fixed_lines[insert_index:insert_index] = stubs

        fixed_content = "\n".join(fixed_lines)
        if fixed_content != content:
            py_file.write_text(fixed_content, encoding="utf-8")


def _collect_schemas_recursively(
    name: str, components: dict[str, object], collected: dict[str, object] | None = None
) -> dict[str, object]:
    """Collect a named schema and all schemas it references via $ref, recursively."""
    if collected is None:
        collected = {}
    if name in collected:
        return collected
    schema = components.get(name)
    if not schema:
        return collected
    collected[name] = schema

    def _find_refs(obj: object) -> None:
        if isinstance(obj, dict):
            ref = obj.get("$ref")
            if isinstance(ref, str) and ref.startswith("#/components/schemas/"):
                _collect_schemas_recursively(ref.split("/")[-1], components, collected)
            for v in obj.values():
                _find_refs(v)
        elif isinstance(obj, list):
            for item in obj:
                _find_refs(item)

    _find_refs(schema)
    return collected


def _find_defined_types(content: str) -> tuple[set[str], set[str]]:
    """Parse generated output to find defined type names and broken nullable TypeAliases.

    Returns:
        Tuple of (all defined type names, type names with TypeAlias = None).
    """
    defined_types: set[str] = set()
    nullable_none_types: set[str] = set()
    for line in content.split("\n"):
        if ": TypeAlias = " in line:
            match = re.match(r"^(\w+):\s*TypeAlias\s*=\s*(.+)$", line)
            if match:
                type_name, type_value = match.group(1), match.group(2).strip()
                defined_types.add(type_name)
                if type_value == "None":
                    nullable_none_types.add(type_name)
        elif line.startswith("class "):
            match = re.match(r"^class\s+(\w+)", line)
            if match:
                defined_types.add(match.group(1))
    return defined_types, nullable_none_types


def _collect_missing_schemas(
    openapi_original: Path,
    missing: set[str],
    defined_types: set[str],
    nullable_none_types: set[str],
) -> dict[str, object]:
    """Collect OpenAPI schemas for missing types and their dependencies.

    Returns:
        Dict of schema_name -> schema_def ready for generation, or empty dict if nothing to generate.
    """
    openapi = json.loads(openapi_original.read_text())
    components = openapi.get("components", {}).get("schemas", {})

    schemas_to_generate: dict[str, object] = {}
    for model_name in missing:
        snake_name = camel_to_snake(model_name)
        _collect_schemas_recursively(snake_name, components, schemas_to_generate)

    if not schemas_to_generate:
        return {}

    nullable_none_snake = {camel_to_snake(t) for t in nullable_none_types}
    return {
        schema_name: schema_def
        for schema_name, schema_def in schemas_to_generate.items()
        if re.sub(r"(?:^|_)(\w)", lambda m: m.group(1).upper(), schema_name) not in defined_types
        or schema_name in nullable_none_snake
    }


def _generate_from_mini_spec(schemas: dict[str, object]) -> str:
    """Generate Python code from a mini OpenAPI spec containing only the given schemas.

    Returns:
        Generated Python source code as a string.
    """
    mini_spec = {
        "openapi": "3.1.0",
        "info": {"title": "missing-types", "version": "0.0.1"},
        "paths": {},
        "components": {"schemas": schemas},
    }

    spec_fd, spec_path = tempfile.mkstemp(suffix=".json")
    os.close(spec_fd)
    tmp_spec = Path(spec_path)
    tmp_spec.write_text(json.dumps(mini_spec))

    tmp_fd, tmp_output_str = tempfile.mkstemp(suffix=".py")
    os.close(tmp_fd)
    tmp_output = Path(tmp_output_str)
    try:
        generate(tmp_spec, output=tmp_output, **_GENERATE_KWARGS)
        return tmp_output.read_text(encoding="utf-8")
    finally:
        tmp_spec.unlink(missing_ok=True)
        tmp_output.unlink(missing_ok=True)


def _patch_output(
    content: str,
    code_blocks: list[str],
    regenerated_aliases: dict[str, str],
) -> str:
    """Splice generated classes and fixed TypeAliases into the existing output content.

    Classes are inserted BEFORE the TypeAlias lines that reference them to avoid NameError.

    Returns:
        Patched content string.
    """
    if code_blocks and regenerated_aliases:
        class_insertion = "\n# Generated from original OpenAPI spec for types lost during flattening\n"
        class_insertion += "\n".join(code_blocks) + "\n\n"

        earliest_pos = len(content)
        for type_name in regenerated_aliases:
            match = re.search(
                rf"^{re.escape(type_name)}:\s*TypeAlias\s*=\s*None$",
                content,
                flags=re.MULTILINE,
            )
            if match and match.start() < earliest_pos:
                earliest_pos = match.start()

        content = content[:earliest_pos] + class_insertion + content[earliest_pos:]

    elif code_blocks:
        insertion = "\n# Generated from original OpenAPI spec for types lost during flattening\n"
        insertion += "\n".join(code_blocks) + "\n"
        insert_pos = content.rfind("\n\n# Stub classes")
        if insert_pos == -1:
            insert_pos = content.rfind("\n\n{")
            if insert_pos == -1:
                insert_pos = len(content)
        content = content[:insert_pos] + insertion + content[insert_pos:]

    for type_name, new_line in regenerated_aliases.items():
        content = re.sub(
            rf"^{re.escape(type_name)}:\s*TypeAlias\s*=\s*None$",
            new_line,
            content,
            flags=re.MULTILINE,
        )

    return content


def generate_missing_types(
    output_file: Path,
    openapi_original: Path,
    used_models: set[str],
) -> None:
    """Generate full class definitions for types referenced in API description but missing from generated output.

    When types are generated from a flattened OpenAPI spec, named schemas lose their identity
    because $ref pointers are inlined. This function detects such missing types, finds their
    definitions in the original (non-flattened) OpenAPI spec, and generates proper classes
    using datamodel-code-generator.

    Args:
        output_file: The generated Python file to patch.
        openapi_original: Path to the original (non-flattened) OpenAPI JSON with named schemas.
        used_models: Set of PascalCase type names referenced in the API description dict.
    """
    content = output_file.read_text(encoding="utf-8")

    defined_types, nullable_none_types = _find_defined_types(content)

    missing = used_models - defined_types
    missing |= nullable_none_types & used_models
    if not missing:
        return

    schemas_for_generation = _collect_missing_schemas(openapi_original, missing, defined_types, nullable_none_types)
    if not schemas_for_generation:
        return

    generated = _generate_from_mini_spec(schemas_for_generation)

    # Extract class definitions and TypeAlias definitions (skip imports/header)
    code_blocks: list[str] = []
    regenerated_aliases: dict[str, str] = {}
    lines = generated.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("class "):
            match = re.match(r"^class\s+(\w+)", line)
            if match and (match.group(1) not in defined_types or match.group(1) in nullable_none_types):
                block = [line]
                i += 1
                while i < len(lines) and (lines[i].startswith("    ") or lines[i].strip() == ""):
                    block.append(lines[i])
                    i += 1
                code_blocks.append("\n".join(block))
                continue
        elif ": TypeAlias = " in line:
            alias_match = re.match(r"^(\w+):\s*TypeAlias\s*=\s*(.+)$", line)
            if alias_match and alias_match.group(1) in nullable_none_types:
                regenerated_aliases[alias_match.group(1)] = line
        i += 1

    if regenerated_aliases or code_blocks:
        content = _patch_output(content, code_blocks, regenerated_aliases)
        output_file.write_text(content, encoding="utf-8")


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
