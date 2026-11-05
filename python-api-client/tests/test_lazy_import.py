# private-test-exempt: asserts each public re-export is the same object as its hiveio_api_client._utilities.smart_lazy_import original (wax-spec-generator#19 acceptance criteria)
from __future__ import annotations

import importlib
import sys
import textwrap
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType
from typing import Final

import pytest

from hiveio_api_client import lazy_import
from hiveio_api_client._utilities import smart_lazy_import

_PACKAGE: Final[str] = "lazy_sample_package"


@pytest.fixture
def lazy_package(tmp_path: Path) -> Iterator[ModuleType]:
    package = tmp_path / _PACKAGE
    package.mkdir()
    (package / "__init__.py").write_text(
        textwrap.dedent(
            """
            from hiveio_api_client.lazy_import import aggregate_same_import, lazy_module_factory

            __all__ = ["first", "second", "third"]

            __getattr__ = lazy_module_factory(
                globals(),
                *aggregate_same_import("first", ("second", "second_alias"), module="lazy_sample_package.values"),
                ("lazy_sample_package.other_values", "third"),
            )
            """
        ),
        encoding="utf-8",
    )
    (package / "values.py").write_text("first = 1\nsecond = 2\n", encoding="utf-8")
    (package / "other_values.py").write_text("third = 3\n", encoding="utf-8")
    sys.path.insert(0, str(tmp_path))
    yield importlib.import_module(_PACKAGE)
    sys.path.remove(str(tmp_path))
    for name in [name for name in sys.modules if name.split(".")[0] == _PACKAGE]:
        del sys.modules[name]


def test_public_helpers_are_the_private_implementations() -> None:
    # ACT
    exported = {name: getattr(lazy_import, name) for name in lazy_import.__all__}

    # ASSERT
    assert exported["lazy_module_factory"] is smart_lazy_import.lazy_module_factory
    assert exported["aggregate_same_import"] is smart_lazy_import.aggregate_same_import
    assert exported["smart_lazy_getattr"] is smart_lazy_import.smart_lazy_getattr
    assert exported["ModuleGlobals"] is smart_lazy_import.ModuleGlobals
    assert exported["ModuleInterfaceMappingInput"] is smart_lazy_import.ModuleInterfaceMappingInput


def test_attribute_access_imports_its_module_on_first_use(lazy_package: ModuleType) -> None:
    # ARRANGE
    assert f"{_PACKAGE}.values" not in sys.modules

    # ACT
    first = lazy_package.first

    # ASSERT
    assert first == 1
    assert f"{_PACKAGE}.values" in sys.modules
    assert f"{_PACKAGE}.other_values" not in sys.modules
    assert lazy_package.second_alias == 2
    assert lazy_package.third == 3


def test_unknown_attribute_raises_attribute_error(lazy_package: ModuleType) -> None:
    # ACT & ASSERT
    with pytest.raises(AttributeError, match="has no attribute 'missing'"):
        _ = lazy_package.missing


def test_missing_translation_of_exported_name_raises_import_error() -> None:
    # ACT & ASSERT
    with pytest.raises(ImportError, match="Missing translations for: unmapped"):
        lazy_import.lazy_module_factory({"__name__": "sample", "__all__": ["unmapped"]})
