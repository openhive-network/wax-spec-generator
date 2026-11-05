"""
Lazy imports of module attributes - a package `__init__.py` assigns `__getattr__` mapping each name of its `__all__`
to the module defining it, so that module is imported only when the name is accessed for the first time.

```python
from __future__ import annotations

from typing import TYPE_CHECKING

from hiveio_api_client.lazy_import import aggregate_same_import, lazy_module_factory

if TYPE_CHECKING:
    from my_package.database_api.database_api_client import DatabaseApi
    from my_package.database_api.database_api_description import FindAccountsResponse

__all__ = ["DatabaseApi", "FindAccountsResponse"]

__getattr__ = lazy_module_factory(
    globals(),
    *aggregate_same_import("DatabaseApi", module="my_package.database_api.database_api_client"),
    ("my_package.database_api.database_api_description", "FindAccountsResponse"),
)
```

`lazy_module_factory` raises `ImportError` when a name of `__all__` has no translation; the created `__getattr__`
raises `AttributeError` for names that are neither translated nor aliased.
"""

from __future__ import annotations

from hiveio_api_client._utilities.smart_lazy_import import (
    AggregatedAliasedImportInput,
    AggregatedModuleInterfaceMappingInput,
    Alias,
    AliasedImportInput,
    AliasMapping,
    GetattrProtocol,
    ImportInput,
    ModuleComponent,
    ModuleGlobals,
    ModuleInterfaceMapping,
    ModuleInterfaceMappingInput,
    ModulePath,
    aggregate_same_import,
    lazy_module_factory,
    smart_lazy_getattr,
)

__all__ = [
    "AggregatedAliasedImportInput",
    "AggregatedModuleInterfaceMappingInput",
    "Alias",
    "AliasMapping",
    "AliasedImportInput",
    "GetattrProtocol",
    "ImportInput",
    "ModuleComponent",
    "ModuleGlobals",
    "ModuleInterfaceMapping",
    "ModuleInterfaceMappingInput",
    "ModulePath",
    "aggregate_same_import",
    "lazy_module_factory",
    "smart_lazy_getattr",
]
