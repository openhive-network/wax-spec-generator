from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Final


MODEL_CLASS_REGEX: Final[str] = r"class\s+([A-Za-z0-9_]+)\([^)]*\):((?:\n(?:    .*)*)*)"
"""Any generated model class (msgspec struct with or without custom base, dataclass)."""
STRUCT_CLASS_REGEX: Final[str] = MODEL_CLASS_REGEX  # kept for backward compatibility
ALIAS_REGEX: Final[str] = r"^([A-Za-z0-9_]+)(?::\s*TypeAlias)?\s*=\s*([^\n]+)"
MULTILINE_ALIAS_REGEX: Final[str] = r"^([A-Za-z0-9_]+)(?::\s*TypeAlias)?\s*=\s*\(\n((?:.*\n)*?\))"
ATTRIBUTE_REGEX: Final[str] = r"\b([A-Z][A-Za-z0-9_]+)\b"


def parse_models_and_aliases(content: str) -> dict[str, set[str]]:
    """Finds all class and alias definitions in the content and builds a dependency map."""
    try:
        return _parse_models_and_aliases_ast(content)
    except SyntaxError:
        return _parse_models_and_aliases_regex(content)


def _parse_models_and_aliases_ast(content: str) -> dict[str, set[str]]:
    """
    Dependencies taken only from code (field annotations, defaults, alias values, class bases).

    Unlike the regex variant, capitalized words in docstrings are not mistaken for model references.
    """
    dependency_map: dict[str, set[str]] = {}
    for node in ast.parse(content).body:
        if isinstance(node, ast.ClassDef):
            expressions: list[ast.AST] = [*node.bases, *node.keywords]
            for statement in node.body:
                if isinstance(statement, ast.AnnAssign):
                    expressions.append(statement.annotation)
                    if statement.value is not None:
                        expressions.append(statement.value)
            dependency_map[node.name] = _referenced_names(expressions) - {node.name}
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.value is not None:
            dependency_map[node.target.id] = _referenced_names([node.value]) - {node.target.id}
        elif isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            dependency_map[node.targets[0].id] = _referenced_names([node.value]) - {node.targets[0].id}
    return dependency_map


def _referenced_names(expressions: list[ast.AST]) -> set[str]:
    names: set[str] = set()
    for expression in expressions:
        for child in ast.walk(expression):
            if isinstance(child, ast.Name) and re.fullmatch(ATTRIBUTE_REGEX, child.id):
                names.add(child.id)
            elif isinstance(child, ast.Constant) and isinstance(child.value, str):  # forward references
                names.update(re.findall(ATTRIBUTE_REGEX, child.value))
    return names


def _parse_models_and_aliases_regex(content: str) -> dict[str, set[str]]:
    """Fallback for content which is not valid python - dependencies found by regexes (also in docstrings)."""
    dependency_map: dict[str, set[str]] = {}  # class_name: set of dependencies
    class_defs = re.findall(MODEL_CLASS_REGEX, content)

    for name, body in class_defs:
        refs = re.findall(ATTRIBUTE_REGEX, body)  # Searching for attributes
        dependency_map[name] = set(refs) - {name}  # Include dependencies, excluding self-references

    alias_defs = re.findall(ALIAS_REGEX, content, re.MULTILINE)
    for name, expr in alias_defs:
        if expr.rstrip().endswith("("):
            continue  # Skip incomplete match — will be caught by multiline regex
        refs = re.findall(ATTRIBUTE_REGEX, expr)
        dependency_map[name] = set(refs) - {name}

    multiline_alias_defs = re.findall(MULTILINE_ALIAS_REGEX, content, re.MULTILINE)
    for name, expr in multiline_alias_defs:
        refs = re.findall(ATTRIBUTE_REGEX, expr)
        dependency_map[name] = set(refs) - {name}

    return dependency_map


def collect_used(dependency_map: dict[str, set[str]], roots: set[str]) -> set[str]:
    """Collects all models and aliases that are used in the such module."""
    used = set(roots)
    models_stack = list(roots)
    while models_stack:
        current = models_stack.pop()
        for dep in dependency_map.get(current, []):
            if dep not in used:
                used.add(dep)
                models_stack.append(dep)
    return used


def remove_multiline_typelines(content: str, unused_aliases: set[str]) -> str:
    """Removes multiline type lines for unused aliases."""

    lines = content.splitlines(keepends=True)
    result_lines = []
    skip = False
    skip_terminator: str | None = None

    for line in lines:
        stripped = line.strip()
        if not skip:
            is_bracket = False
            is_paren = False
            for alias in unused_aliases:
                if (
                    stripped.startswith(f"{alias} = list[")
                    or stripped.startswith(f"{alias} = Optional[")
                    or stripped.startswith(f"{alias}: TypeAlias = list[")
                    or stripped.startswith(f"{alias}: TypeAlias = Optional[")
                ):
                    is_bracket = True
                    break
                if stripped.startswith(f"{alias} = (") or stripped.startswith(f"{alias}: TypeAlias = ("):
                    is_paren = True
                    break
            if not is_bracket and not is_paren:
                if stripped.startswith("list[") or stripped.startswith("Optional["):
                    is_bracket = True
            if is_bracket or is_paren:
                skip = True
                skip_terminator = ")" if is_paren else "]"
                continue
            result_lines.append(line)
        else:
            if skip_terminator == "]" and "]" in line:
                skip = False
                continue
            if skip_terminator == ")" and stripped == ")":
                skip = False
                continue
    return "".join(result_lines)


def clean_file(path: Path, roots: set[str]) -> None:
    """Cleans the file at the given path by removing unused class and alias definitions."""

    content = path.read_text()
    dependency_map = parse_models_and_aliases(content)
    used = collect_used(dependency_map, roots)

    for name in dependency_map.keys():
        if name not in used:
            class_pattern = re.compile(
                rf"^(?:@dataclass(?:\([^)\n]*\))?\n)?class {re.escape(name)}\([^)]*\):(?:\n(?:(?:    .*)|\s*\"\"\".*\"\"\"))*",
                re.MULTILINE,
            )
            content = class_pattern.sub("", content)

            # Remove multiline aliases FIRST: Name: TypeAlias = (\n    ...\n)
            # Must run before single-line removal to avoid breaking multiline patterns
            multiline_alias_pattern = re.compile(
                rf"^\s*{re.escape(name)}(?::\s*TypeAlias)?\s*=\s*\(\n(?:.*\n)*?\)\n?", re.MULTILINE
            )
            content = multiline_alias_pattern.sub("", content)
            # Remove single-line aliases
            alias_pattern = re.compile(rf"^\s*{re.escape(name)}(?::\s*TypeAlias)?\s*=\s*[^\n]+\n?", re.MULTILINE)
            content = alias_pattern.sub("", content)

    unused_aliases = {name for name in dependency_map.keys() if name not in used}
    content = remove_multiline_typelines(content, unused_aliases)

    content = re.sub(r"^\s*list\[.*\]\s*$", "", content, flags=re.MULTILINE)
    # Remove lines like list[SomeType]

    content = re.sub(r"^\s*Optional\[.*\]\s*$", "", content, flags=re.MULTILINE)
    # Remove lines like list[SomeType] or Optional[SomeType]

    content = re.sub(r"^\s*[A-Z][A-Za-z0-9_]+\s*$", "", content, flags=re.MULTILINE)
    # Remove lines like SomeType

    content = re.sub(r"^\s*\]\s*$", "", content, flags=re.MULTILINE)
    # Remove excessive ]

    content = re.sub(r"\n{3,}", "\n\n", content)
    path.write_text(content)
