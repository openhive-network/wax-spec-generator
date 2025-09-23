from __future__ import annotations

import re
from pathlib import Path
from typing import Final


STRUCT_CLASS_REGEX: Final[str] = r"class\s+([A-Za-z0-9_]+)\(Struct\):((?:\n(?:    .*)*)*)"
ALIAS_REGEX: Final[str] = r"^([A-Za-z0-9_]+)\s*=\s*([^\n]+)"
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
        refs = re.findall(ATTRIBUTE_REGEX, expr)
        dependency_map[name] = set(refs) - {name}

    return dependency_map


def collect_used(dependency_map: dict[str, set[str]], roots: set[str]) -> set[str]:
    used = set(roots)
    queue = list(roots)
    while queue:
        current = queue.pop()
        for dep in dependency_map.get(current, []):
            if dep not in used:
                used.add(dep)
                queue.append(dep)
    return used


def remove_multiline_typelines(content: str, unused_aliases: set[str]) -> str:
    lines = content.splitlines(keepends=True)
    result_lines = []
    skip = False

    for line in lines:
        stripped = line.strip()
        if not skip:
            if any(
                stripped.startswith(f"{alias} = list[") or stripped.startswith(f"{alias} = Optional[")
                for alias in unused_aliases
            ):
                skip = True
                continue
            if stripped.startswith("list[") or stripped.startswith("Optional["):
                skip = True
                continue
            result_lines.append(line)
        else:
            if "]" in line:
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

            alias_pattern = re.compile(rf"^\s*{re.escape(name)}\s*=\s*[^\n]+\n?", re.MULTILINE)
            content = alias_pattern.sub("", content)

    unused_aliases = {name for name in dependency_map.keys() if name not in used}
    content = remove_multiline_typelines(content, unused_aliases)

    content = re.sub(r"^\s*list\[.*\]\s*$", "", content, flags=re.MULTILINE)
    content = re.sub(r"^\s*Optional\[.*\]\s*$", "", content, flags=re.MULTILINE)
    content = re.sub(r"^\s*[A-Z][A-Za-z0-9_]+\s*$", "", content, flags=re.MULTILINE)
    content = re.sub(r"^\s*\]\s*$", "", content, flags=re.MULTILINE)

    content = re.sub(r"\n{3,}", "\n\n", content)

    path.write_text(content)
