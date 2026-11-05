from __future__ import annotations

import ast
import json
from collections import Counter
from typing import TYPE_CHECKING, Final

import pytest

from api_client_generator.exceptions import MethodNameCollisionError
from api_client_generator.rest import generate_api_client_from_swagger
from tests.base_api_classes import MockAsyncRestApiBase
from tests.generate_clients_and_collections import OPENAPI_REST_DEFINITION_DESTINATION

if TYPE_CHECKING:
    from pathlib import Path

_STRING_RESPONSE: Final[dict[str, object]] = {"200": {"content": {"application/json": {"schema": {"type": "string"}}}}}


def _operation(*path_params: str) -> dict[str, object]:
    return {
        "tags": ["test"],
        "summary": "test",
        "description": "test",
        "operationId": "test",
        "parameters": [
            {"name": name, "in": "path", "required": True, "schema": {"type": "string"}} for name in path_params
        ],
        "responses": _STRING_RESPONSE,
    }


def _generate(tmp_path: Path, openapi_file: Path) -> str:
    generate_api_client_from_swagger(openapi_file, tmp_path, base_class=MockAsyncRestApiBase)  # type: ignore[arg-type]
    return (tmp_path / "test_api_client.py").read_text()


def _generate_from(tmp_path: Path, paths: dict[str, dict[str, object]]) -> str:
    openapi_file = tmp_path / "openapi.json"
    openapi_file.write_text(
        json.dumps(
            {
                "openapi": "3.1.0",
                "info": {"title": "test", "version": "1"},
                "servers": [{"url": "/test-api"}],
                "paths": paths,
            }
        )
    )
    return _generate(tmp_path, openapi_file)


def _methods(source: str) -> dict[str, tuple[str, list[str]]]:
    """Generated endpoints: name -> (decorator, positional arguments), failing when a name is defined twice."""
    class_def = next(node for node in ast.parse(source).body if isinstance(node, ast.ClassDef))
    functions = [
        node
        for node in class_def.body
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node.decorator_list
    ]
    duplicates = [name for name, count in Counter(function.name for function in functions).items() if count > 1]
    assert not duplicates, f"shadowed methods: {duplicates}"
    return {
        function.name: (ast.unparse(function.decorator_list[0]), [arg.arg for arg in function.args.args[1:]])
        for function in functions
    }


def test_nested_paths_get_names_with_their_path_params(tmp_path: Path) -> None:
    # ACT
    methods = _methods(
        _generate_from(
            tmp_path,
            {
                "/posts": {"get": _operation()},
                "/posts/{author}/{permlink}": {"get": _operation("author", "permlink")},
                "/communities": {"get": _operation()},
                "/communities/{name}": {"get": _operation("name")},
            },
        )
    )

    # ASSERT
    assert methods == {
        "posts": ("endpoint_rest.get('/posts')", []),
        "posts_by_author_permlink": ("endpoint_rest.get('/posts/{author}/{permlink}')", ["author", "permlink"]),
        "communities": ("endpoint_rest.get('/communities')", []),
        "communities_by_name": ("endpoint_rest.get('/communities/{name}')", ["name"]),
    }


def test_get_keeps_name_of_path_with_several_methods(tmp_path: Path) -> None:
    # ACT
    methods = _methods(
        _generate_from(
            tmp_path,
            {"/accounts/{account-name}": {"post": _operation("account-name"), "get": _operation("account-name")}},
        )
    )

    # ASSERT
    assert methods == {
        "accounts_post": ("endpoint_rest.post('/accounts/{account-name}')", ["account_name"]),
        "accounts": ("endpoint_rest.get('/accounts/{account-name}')", ["account_name"]),
    }


def test_unique_names_are_unchanged(tmp_path: Path) -> None:
    # ACT
    methods = _methods(_generate(tmp_path, OPENAPI_REST_DEFINITION_DESTINATION))

    # ASSERT
    assert {name: decorator for name, (decorator, _) in methods.items()} == {
        "test_2": "endpoint_rest.get('/test-2')",
        "test_balances": "endpoint_rest.get('/test/{test-name}/balances')",
    }


def test_unresolvable_collision_names_both_operations(tmp_path: Path) -> None:
    # ACT & ASSERT
    with pytest.raises(MethodNameCollisionError) as error:
        _generate_from(tmp_path, {"/test-2": {"get": _operation()}, "/test_2": {"get": _operation()}})

    assert error.value.collisions == {"test_2": (("/test-2", "get"), ("/test_2", "get"))}
    assert "GET /test-2, GET /test_2" in error.value.message
    assert not (tmp_path / "test_api_client.py").exists()
