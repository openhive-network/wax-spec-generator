from __future__ import annotations

import re
from pathlib import Path

from datamodel_code_generator import DataModelType, InputFileType, PythonVersion, generate

from api_client_generator._private.resolve_needed_imports import (
    compute_full_module_name,
    find_package_root,
)


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
        output_model_type=DataModelType.MsgspecStruct,
        input_file_type=InputFileType.OpenAPI,
        use_field_description=True,
        use_standard_collections=True,
        use_exact_imports=True,
        target_python_version=PythonVersion.PY_311,  # Use 3.11 to avoid PEP 695 type statements (not compatible with exec_module)
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
