from __future__ import annotations

import ast
import re
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from pathlib import Path

ATTRIBUTE_REGEX: Final[str] = r"\b([A-Z][A-Za-z0-9_]+)\b"


def parse_models_and_aliases(content: str) -> dict[str, set[str]]:
    """
    Dependencies of the models and aliases defined in the content (class name / alias name -> referenced names).

    Dependencies are taken only from code (field annotations, defaults, alias values, class bases) - capitalized words
    in docstrings are not mistaken for model references.
    """
    return {name: _referenced_names(node) - {name} for name, node in _definitions(ast.parse(content))}


def _definitions(module: ast.Module) -> list[tuple[str, ast.stmt]]:
    """Models and aliases defined at the top level of the module."""
    definitions: list[tuple[str, ast.stmt]] = []
    for node in module.body:
        if isinstance(node, ast.ClassDef):
            definitions.append((node.name, node))
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.value is not None:
            definitions.append((node.target.id, node))
        elif isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            definitions.append((node.targets[0].id, node))
    return definitions


def _referenced_names(node: ast.stmt) -> set[str]:
    expressions: list[ast.AST] = []
    if isinstance(node, ast.ClassDef):
        expressions += [*node.bases, *node.keywords]
        for statement in node.body:
            if isinstance(statement, ast.AnnAssign):
                expressions.append(statement.annotation)
                if statement.value is not None:
                    expressions.append(statement.value)
    elif isinstance(node, ast.AnnAssign | ast.Assign) and node.value is not None:
        expressions.append(node.value)

    names: set[str] = set()
    for expression in expressions:
        for child in ast.walk(expression):
            if isinstance(child, ast.Name) and re.fullmatch(ATTRIBUTE_REGEX, child.id):
                names.add(child.id)
            elif isinstance(child, ast.Constant) and isinstance(child.value, str):  # forward references
                names.update(re.findall(ATTRIBUTE_REGEX, child.value))
    return names


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


def clean_file(path: Path, roots: set[str]) -> None:
    """
    Remove the models and aliases of the module which the given ones (roots) do not use, directly or indirectly.

    Definitions are removed with their decorators (e.g. `@dataclass`) and docstrings of aliases.
    """
    content = path.read_text()
    module = ast.parse(content)
    used = collect_used(parse_models_and_aliases(content), roots)
    names = {id(node): name for name, node in _definitions(module)}

    removed_lines: set[int] = set()
    for index, node in enumerate(module.body):
        name = names.get(id(node))
        if name is None or name in used:
            continue
        lines_of_node = definition_lines(node)
        following = module.body[index + 1] if index + 1 < len(module.body) else None
        if not isinstance(node, ast.ClassDef) and _is_docstring(following):
            assert following is not None
            lines_of_node = range(lines_of_node.start, (following.end_lineno or following.lineno) + 1)
        removed_lines.update(lines_of_node)

    lines = content.splitlines(keepends=True)
    kept = "".join(line for number, line in enumerate(lines, start=1) if number not in removed_lines)
    path.write_text(re.sub(r"\n{3,}", "\n\n", kept))


def definition_lines(node: ast.stmt) -> range:
    """Numbers of lines of the top-level definition, with its decorators (e.g. `@dataclass`)."""
    start = min([node.lineno, *(decorator.lineno for decorator in getattr(node, "decorator_list", []))])
    return range(start, (node.end_lineno or node.lineno) + 1)


def _is_docstring(node: ast.stmt | None) -> bool:
    return isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str)
