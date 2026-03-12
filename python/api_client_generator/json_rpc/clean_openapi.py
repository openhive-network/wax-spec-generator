from __future__ import annotations

import re
from pathlib import Path
from typing import Final


STRUCT_CLASS_REGEX: Final[str] = r"class\s+([A-Za-z0-9_]+)\(Struct\):((?:\n(?:    .*)*)*)"
ALIAS_REGEX: Final[str] = r"^([A-Za-z0-9_]+)(?::\s*TypeAlias)?\s*=\s*([^\n]+)"
MULTILINE_ALIAS_REGEX: Final[str] = r"^([A-Za-z0-9_]+)(?::\s*TypeAlias)?\s*=\s*\(\n((?:.*\n)*?\))"
ATTRIBUTE_REGEX: Final[str] = r"\b([A-Z][A-Za-z0-9_]+)\b"


def parse_models_and_aliases(content: str) -> dict[str, set[str]]:
    """Finds all class and alias definitions in the content and builds a dependency map."""

    dependency_map: dict[str, set[str]] = {}  # class_name: set of dependencies
    class_defs = re.findall(STRUCT_CLASS_REGEX, content)

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
                rf"^class {re.escape(name)}\(Struct\):(?:\n(?:(?:    .*)|\s*\"\"\".*\"\"\"))*", re.MULTILINE
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
