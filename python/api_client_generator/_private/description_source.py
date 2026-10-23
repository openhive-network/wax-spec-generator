"""Source code of description modules - names under which params and results of endpoints are written there."""

from __future__ import annotations

import ast
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from api_client_generator._private.common.models_aliased import ApiDescription

_DESCRIBED_KEYS: tuple[str, ...] = ("params", "result")


@dataclass(frozen=True)
class NamedAnnotation:
    """An annotation written by its name (e.g. an alias `AccountName` of `str`), imported from its module."""

    name: str
    module: str
    value: object
    """The annotation itself."""


def find_dict(module: ast.Module, name: str) -> tuple[ast.stmt, ast.Dict] | None:
    """The top-level assignment of a dict to the name and the dict."""
    for statement in module.body:
        targets: list[ast.expr]
        value: ast.expr | None
        if isinstance(statement, ast.Assign):
            targets, value = statement.targets, statement.value
        elif isinstance(statement, ast.AnnAssign):
            targets, value = [statement.target], statement.value
        else:
            continue
        if isinstance(value, ast.Dict) and any(
            isinstance(target, ast.Name) and target.id == name for target in targets
        ):
            return statement, value
    return None


def with_alias_names(api_description: ApiDescription) -> ApiDescription:
    """
    The description with params and results written by names of aliases replaced by `NamedAnnotation`s.

    Aliases (e.g. `X: TypeAlias = list[str]`) do not exist at runtime - without their names, clients would refer to
    the aliased annotations (e.g. `str` instead of `AccountName`). Names are taken from the source of the module
    defining the description (imported before the client is generated); classes keep referring to themselves.
    """
    names = _names_in_source(api_description)
    if names is None:
        return api_description
    module, written = names
    return {
        api: {
            endpoint: {
                key: NamedAnnotation(written[api, endpoint, key], module, value)
                if (api, endpoint, key) in written and value is not None and not isinstance(value, type)
                else value
                for key, value in fields.items()
            }
            for endpoint, fields in endpoints.items()
        }
        for api, endpoints in api_description.items()
    }


def _names_in_source(api_description: ApiDescription) -> tuple[str, dict[tuple[str, str, str], str]] | None:
    """The module defining the description and names of params and results written in it (api, endpoint, key)."""
    for module_name, module in list(sys.modules.items()):
        variables = [name for name, value in list(getattr(module, "__dict__", {}).items()) if value is api_description]
        file = getattr(module, "__file__", None)
        if not variables or not isinstance(file, str) or not file.endswith(".py"):
            continue
        found = find_dict(ast.parse(Path(file).read_text(encoding="utf-8")), variables[0])
        if found is not None:
            return module_name, _written_names(found[1])
    return None


def _written_names(description: ast.Dict) -> dict[tuple[str, str, str], str]:
    names: dict[tuple[str, str, str], str] = {}
    for api, endpoints in zip(description.keys, description.values, strict=True):
        if not isinstance(api, ast.Constant) or not isinstance(endpoints, ast.Dict):
            continue
        for endpoint, fields in zip(endpoints.keys, endpoints.values, strict=True):
            if not isinstance(endpoint, ast.Constant) or not isinstance(fields, ast.Dict):
                continue
            for key, value in zip(fields.keys, fields.values, strict=True):
                if isinstance(key, ast.Constant) and key.value in _DESCRIBED_KEYS and isinstance(value, ast.Name):
                    names[str(api.value), str(endpoint.value), str(key.value)] = value.id
    return names
