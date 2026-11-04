from __future__ import annotations

import ast
import subprocess
import sys
import textwrap
from pathlib import Path
from typing import Final

import hiveio_api_client

PACKAGE_DIRECTORY: Final[Path] = Path(hiveio_api_client.__file__).parent
FOREIGN_PACKAGES: Final[frozenset[str]] = frozenset({"beekeepy", "hiveio_api", "schemas"})


def test_all_exported_names_are_importable() -> None:
    # ACT
    exported = {name: getattr(hiveio_api_client, name) for name in hiveio_api_client.__all__}

    # ASSERT
    assert exported["AbstractAsyncApi"].__module__ == "hiveio_api_client._apis.abc.api"
    assert exported["AsyncRemoteHandle"].__name__ == "AsyncRemoteHandle"


def test_importing_the_package_imports_no_foreign_package() -> None:
    # ARRANGE - a fresh interpreter, modules imported by other tests do not count
    script = textwrap.dedent(
        f"""
        import sys
        import hiveio_api_client
        for name in hiveio_api_client.__all__:
            getattr(hiveio_api_client, name)
        print(sorted({{module.split(".")[0] for module in sys.modules}} & {FOREIGN_PACKAGES!r}))
        """
    )

    # ACT
    output = subprocess.run([sys.executable, "-c", script], check=True, capture_output=True, text=True).stdout

    # ASSERT
    assert output.strip() == "[]"


def test_package_source_does_not_import_foreign_packages() -> None:
    # ARRANGE
    imported: set[tuple[str, str]] = set()

    # ACT
    for source in PACKAGE_DIRECTORY.rglob("*.py"):
        for node in ast.walk(ast.parse(source.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                imported |= {(source.name, alias.name) for alias in node.names}
            elif isinstance(node, ast.ImportFrom) and node.module is not None and node.level == 0:
                imported.add((source.name, node.module))

    # ASSERT
    foreign = {(file, module) for file, module in imported if module.split(".")[0] in FOREIGN_PACKAGES}
    assert foreign == set()
    assert any(module == "msgspec" for _, module in imported), "The scan has to see imports of the package"
