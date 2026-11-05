from __future__ import annotations

import ast
import importlib
import inspect
from typing import TYPE_CHECKING

import pytest

from api_client_generator import json_rpc, rest
from api_client_generator._private.common import models_aliased
from api_client_generator._private.description_tools import AliasToAssign

if TYPE_CHECKING:
    from collections.abc import Callable
    from types import ModuleType

_PUBLIC_FUNCTIONS = [
    (package, getattr(package, name))
    for package in (json_rpc, rest)
    for name in package.__all__
    if inspect.isfunction(getattr(package, name))
]


def _imported_names(module: ModuleType) -> dict[str, str]:
    tree = ast.parse(inspect.getsource(module))
    return {
        alias.asname or alias.name: node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
        for alias in node.names
    }


def _annotation_names(function: Callable[..., object]) -> set[str]:
    return {
        node.id
        for annotation in function.__annotations__.values()
        for node in ast.walk(ast.parse(annotation, mode="eval"))
        if isinstance(node, ast.Name)
    }


@pytest.mark.parametrize(
    ("public_object", "private_object"),
    [
        (json_rpc.ApiDescription, models_aliased.ApiDescription),
        (json_rpc.BaseApiClass, models_aliased.BaseApiClass),
        (json_rpc.Importable, models_aliased.Importable),
        (json_rpc.AliasToAssign, AliasToAssign),
        (rest.BaseApiClass, models_aliased.BaseApiClass),
    ],
)
def test_public_name_is_the_private_object(public_object: object, private_object: object) -> None:
    assert public_object is private_object


@pytest.mark.parametrize(
    ("package", "function"), _PUBLIC_FUNCTIONS, ids=[function.__name__ for _, function in _PUBLIC_FUNCTIONS]
)
def test_signature_types_are_importable_from_public_package(
    package: ModuleType, function: Callable[..., object]
) -> None:
    origins = _imported_names(importlib.import_module(function.__module__))
    private_names = {name for name in _annotation_names(function) if "_private" in origins.get(name, "").split(".")}

    assert private_names <= set(package.__all__)
    for name in private_names:
        assert getattr(package, name) is getattr(importlib.import_module(origins[name]), name)
