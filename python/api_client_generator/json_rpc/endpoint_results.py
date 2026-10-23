from __future__ import annotations

import ast
from typing import TYPE_CHECKING, Final

from api_client_generator._private.description_source import find_dict

if TYPE_CHECKING:
    from pathlib import Path

ENDPOINT_RESULTS_NAME: Final[str] = "ENDPOINT_RESULTS"


def append_endpoint_results(description_file: Path, description_name: str) -> None:
    """
    Append `ENDPOINT_RESULTS` (method -> (result model, whether the result is an array)) to a generated description.

    The mapping is written out from the description of endpoints of the module (`description_name`), so models of
    results can be looked up by method names (e.g. to validate responses with the models of the module) and type
    checkers see the models themselves. A mapping written before is replaced. Endpoints without a result map to `None`.

    Raises:
        ValueError: If the module does not define the description.
    """
    source = description_file.read_text(encoding="utf-8")
    module = ast.parse(source)
    found = find_dict(module, description_name)
    if found is None:
        raise ValueError(f"The module does not define the description `{description_name}`.")
    entries = [f"    {method!r}: ({result}, {is_array})," for method, result, is_array in _endpoint_results(found[1])]
    if (previous := find_dict(module, ENDPOINT_RESULTS_NAME)) is not None:
        lines = source.splitlines(keepends=True)
        statement = previous[0]
        before = "".join(lines[: statement.lineno - 1]).rstrip("\n") + "\n"
        source = before + "".join(lines[statement.end_lineno or statement.lineno :])
    description_file.write_text(
        f"{source}\n\n{ENDPOINT_RESULTS_NAME} = {{\n" + "".join(f"{entry}\n" for entry in entries) + "}\n",
        encoding="utf-8",
    )


def _endpoint_results(description: ast.Dict) -> list[tuple[str, str, bool]]:
    results: list[tuple[str, str, bool]] = []
    for endpoints in description.values:
        if not isinstance(endpoints, ast.Dict):
            continue
        for method, endpoint in zip(endpoints.keys, endpoints.values, strict=True):
            if not isinstance(method, ast.Constant) or not isinstance(endpoint, ast.Dict):
                continue
            fields = {
                key.value: value
                for key, value in zip(endpoint.keys, endpoint.values, strict=True)
                if isinstance(key, ast.Constant)
            }
            response_array = fields.get("response_array")
            is_array = isinstance(response_array, ast.Constant) and bool(response_array.value)
            result = fields.get("result")
            results.append((str(method.value), "None" if result is None else ast.unparse(result), is_array))
    return results
